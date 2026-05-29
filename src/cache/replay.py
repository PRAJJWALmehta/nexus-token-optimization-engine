"""Cache replay — serve cached responses back to the client.

For streaming requests (``stream=True``):
  :func:`replay_sse_stream` re-yields the stored SSE bytes as an async
  generator, indistinguishable from a live upstream response.

For non-streaming requests (``stream=False``):
  :func:`replay_json_response` deserialises the cached bytes and returns a
  :class:`~fastapi.responses.JSONResponse`.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Maximum chunk size when re-streaming cached bytes (prevents huge single yields)
_CHUNK_SIZE = 4096


async def replay_sse_stream(cached_bytes: bytes) -> AsyncIterator[bytes]:
    """Replay *cached_bytes* as an async SSE byte stream.

    Yields the bytes in chunks of up to :data:`_CHUNK_SIZE` bytes so that
    client-side SSE parsers receive data progressively, matching the behaviour
    of a live upstream stream.

    Parameters
    ----------
    cached_bytes:
        The raw SSE bytes originally captured from the upstream provider.

    Yields
    ------
    bytes
        Chunks of the cached SSE response.
    """
    if not cached_bytes:
        return

    offset = 0
    while offset < len(cached_bytes):
        chunk = cached_bytes[offset : offset + _CHUNK_SIZE]
        yield chunk
        offset += _CHUNK_SIZE


def replay_json_response(
    cached_bytes: bytes,
    extra_headers: dict | None = None,
) -> JSONResponse:
    """Parse *cached_bytes* and return them as a :class:`JSONResponse`.

    Parameters
    ----------
    cached_bytes:
        The raw JSON bytes originally captured from the upstream provider.
    extra_headers:
        Additional HTTP headers to attach (e.g. ``{"X-Cache": "HIT"}``).

    Returns
    -------
    JSONResponse
        A FastAPI response with the cached payload and ``application/json``
        content type.
    """
    try:
        content = json.loads(cached_bytes.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("replay_json_response: failed to parse cached bytes: %s", exc)
        content = {}

    return JSONResponse(content=content, headers=extra_headers or {})
