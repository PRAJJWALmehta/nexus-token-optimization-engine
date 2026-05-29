"""Chat completions router.

Exposes ``POST /v1/chat/completions`` which accepts OpenAI-compatible requests
and — depending on the cache state — either:

* **Cache HIT**:   Replays the cached response (SSE or JSON) without touching
  the upstream provider.  Response carries ``X-Cache: HIT``.
* **Cache MISS**:  Forwards to the configured upstream provider, buffers the
  response stream for cache persistence, and returns it to the client.
  Response carries ``X-Cache: MISS``.
* **Cache BYPASS**: When caching is disabled via config, passes straight through.
  Response carries ``X-Cache: BYPASS``.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.cache.buffer import StreamBuffer
from src.cache.lookup import CacheLookup, CacheResult
from src.cache.replay import replay_json_response, replay_sse_stream
from src.config import Settings, settings
from src.models.chat import ChatCompletionRequest
from src.providers.base import ProviderAdapter
from src.providers.openai import OpenAIProviderAdapter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Provider dependency (unchanged)
# ---------------------------------------------------------------------------


def get_provider() -> ProviderAdapter:
    return OpenAIProviderAdapter(settings)


# ---------------------------------------------------------------------------
# Cache lookup dependency — injected from app lifespan state
# ---------------------------------------------------------------------------


def get_cache_lookup(request: Request) -> Optional[CacheLookup]:
    """Return the shared :class:`CacheLookup` instance from app state.

    Returns ``None`` when caching is disabled or not yet initialised so that
    the route handler can fall back transparently.
    """
    return getattr(request.app.state, "cache_lookup", None)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/v1/chat/completions")
async def chat_completions(
    request_data: ChatCompletionRequest,
    request: Request,
    provider: Annotated[ProviderAdapter, Depends(get_provider)],
    cache_lookup: Annotated[Optional[CacheLookup], Depends(get_cache_lookup)],
):
    """Proxy chat completions to the upstream LLM provider with semantic caching.

    On cache HIT:  replays cached response immediately (no upstream call).
    On cache MISS: forwards to upstream, buffers the stream, persists to cache.
    On BYPASS:     passes straight through to upstream without any cache logic.
    """
    tenant_id: str = getattr(request.state, "tenant_id", "default")

    # ------------------------------------------------------------------ #
    #  1.  Cache check (skipped when lookup is None / disabled)           #
    # ------------------------------------------------------------------ #
    result: CacheResult | None = None
    client_cache_control = request.headers.get("cache-control", "").lower()

    if cache_lookup is not None and "no-cache" not in client_cache_control and "no-store" not in client_cache_control:
        result = await cache_lookup.check(request_data, tenant_id)

        if result.hit:
            logger.info("Serving cache HIT for tenant=%s", tenant_id)

            if request_data.stream:
                return StreamingResponse(
                    replay_sse_stream(result.cached_response),
                    media_type="text/event-stream",
                    headers={"X-Cache": "HIT"},
                )
            else:
                return replay_json_response(
                    result.cached_response,
                    extra_headers={"X-Cache": "HIT"},
                )

    # ------------------------------------------------------------------ #
    #  2.  Cache MISS or BYPASS — forward to upstream                     #
    # ------------------------------------------------------------------ #
    client_bypassed = "no-cache" in client_cache_control or "no-store" in client_cache_control
    x_cache_header = "MISS" if cache_lookup is not None and not client_bypassed else "BYPASS"

    if request_data.stream:
        # Build the on_complete callback to persist the response after delivery
        async def _persist_stream(data: bytes) -> None:
            if cache_lookup is not None and result is not None and result.key is not None:
                await cache_lookup.store(result.key, request_data, data, stream=True)

        buffered = StreamBuffer(
            provider.stream_completions(request_data),
            on_complete=_persist_stream if cache_lookup is not None else None,
        )
        return StreamingResponse(
            buffered,
            media_type="text/event-stream",
            headers={"X-Cache": x_cache_header},
        )
    else:
        # Non-streaming: collect response then optionally cache it
        chunks = []
        async for chunk in provider.stream_completions(request_data):
            chunks.append(chunk)

        body = b"".join(chunks)

        # Persist to cache asynchronously
        if cache_lookup is not None and result is not None and result.key is not None:
            import asyncio
            asyncio.create_task(
                cache_lookup.store(result.key, request_data, body, stream=False)
            )

        return JSONResponse(
            content=json.loads(body),
            headers={"X-Cache": x_cache_header},
        )
