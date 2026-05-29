"""Transparent SSE stream buffer for cache population.

:class:`StreamBuffer` wraps an ``AsyncIterator[bytes]`` from the upstream
provider.  It yields each chunk to the caller **immediately** (zero added
latency) while accumulating chunks in memory.

When the stream ends normally (the upstream sends ``data: [DONE]`` and the
iterator is exhausted), the buffer fires an async callback so the caller can
persist the complete response to the cache.

If the upstream raises an exception mid-stream, the buffer re-raises without
triggering the callback — partial responses MUST NOT be cached.

Usage
-----
::

    async def persist(data: bytes) -> None:
        await cache_store.store(key, embedding, data, stream=True)

    buffered = StreamBuffer(provider.stream_completions(request), on_complete=persist)
    return StreamingResponse(buffered, media_type="text/event-stream")
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class StreamBuffer:
    """Transparent async byte-stream that buffers chunks for cache persistence.

    Parameters
    ----------
    source:
        Upstream async byte iterator (e.g. provider SSE stream).
    on_complete:
        Async callback invoked with the fully assembled bytes once the source
        is exhausted.  Scheduled as a background ``asyncio.create_task`` so it
        does not add latency to the response.
    """

    def __init__(
        self,
        source: AsyncIterator[bytes],
        on_complete: Optional[Callable[[bytes], Awaitable[None]]] = None,
    ) -> None:
        self._source = source
        self._on_complete = on_complete
        self._chunks: list[bytes] = []
        self._error: Optional[Exception] = None

    def __aiter__(self) -> "StreamBuffer":
        return self

    async def __anext__(self) -> bytes:
        """Fetch the next chunk from the upstream source.

        Accumulates each chunk in ``self._chunks`` transparently.
        On natural exhaustion, fires the on_complete callback.
        On error, re-raises without calling the callback.
        """
        try:
            chunk = await self._source.__anext__()
            self._chunks.append(chunk)
            return chunk
        except StopAsyncIteration:
            # Stream finished normally — schedule cache write in background
            assembled = b"".join(self._chunks)
            if self._on_complete and assembled:
                asyncio.create_task(self._fire_callback(assembled))
            raise
        except Exception as exc:
            # Upstream error mid-stream: do NOT persist partial response
            self._error = exc
            logger.warning("StreamBuffer: upstream error during streaming: %s", exc)
            raise

    async def _fire_callback(self, data: bytes) -> None:
        """Execute the on_complete callback, logging any errors."""
        try:
            await self._on_complete(data)
        except Exception as exc:  # pragma: no cover
            logger.warning("StreamBuffer on_complete callback failed: %s", exc)
