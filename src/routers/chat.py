"""Chat completions router.

Exposes ``POST /v1/chat/completions`` which accepts OpenAI-compatible requests
and — depending on the routing and cache state — either:

* **Routing + Cache HIT**:  Replays the cached response (SSE or JSON) without
  touching the upstream provider.  Response carries ``X-Cache: HIT`` and
  ``X-Cached-Model: <resolved-model>`` when the request was routed.
* **Routing + Cache MISS**:  Forwards to the configured upstream provider with
  the resolved model, buffers the response stream for cache persistence.
  Response carries ``X-Cache: MISS`` and ``X-Routed-Model: <resolved-model>``.
* **Cache BYPASS**: When caching is disabled via config, passes straight through.
  Response carries ``X-Cache: BYPASS`` (plus ``X-Routed-Model`` if routed).
* **Routing disabled + trigger model**: Returns ``400 Bad Request`` immediately.
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
from src.models.chat import ChatCompletionRequest, GatewayErrorDetail, GatewayErrorResponse
from src.providers.base import ProviderAdapter
from src.providers.openai import OpenAIProviderAdapter
from src.routing.router import ModelRouter, RoutingDisabledError, RoutingResult

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


# ---------------------------------------------------------------------------
# Provider dependency
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
# Model router dependency
# ---------------------------------------------------------------------------


def get_model_router() -> ModelRouter:
    """Return a :class:`ModelRouter` instance built from app settings."""
    return ModelRouter(settings=settings)


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/v1/chat/completions")
async def chat_completions(
    request_data: ChatCompletionRequest,
    request: Request,
    provider: Annotated[ProviderAdapter, Depends(get_provider)],
    cache_lookup: Annotated[Optional[CacheLookup], Depends(get_cache_lookup)],
    model_router: Annotated[ModelRouter, Depends(get_model_router)],
):
    """Proxy chat completions to the upstream LLM provider.

    Request flow:
    1. Dynamic routing (optional) — resolves ``model: "auto"`` before cache.
    2. Cache check — returns cached response on HIT.
    3. Upstream forward — on MISS/BYPASS, forward to provider and cache result.

    Response headers:
    - ``X-Cache``: HIT / MISS / BYPASS
    - ``X-Routed-Model``: resolved model name (cache MISS/BYPASS, routed only)
    - ``X-Cached-Model``: resolved model name (cache HIT, routed only)
    """
    tenant_id: str = getattr(request.state, "tenant_id", "default")

    # ------------------------------------------------------------------ #
    #  0.  Dynamic routing (before cache — resolves model in place)       #
    # ------------------------------------------------------------------ #
    routing_result: RoutingResult = RoutingResult(routed_model=None)
    try:
        routing_result = model_router.resolve(request_data)
    except RoutingDisabledError as exc:
        return JSONResponse(
            status_code=400,
            content=GatewayErrorResponse(
                error=GatewayErrorDetail(
                    message=str(exc),
                    type="routing_disabled",
                    code="400",
                )
            ).model_dump(),
        )

    # ------------------------------------------------------------------ #
    #  1.  Cache check (skipped when lookup is None / disabled)           #
    # ------------------------------------------------------------------ #
    result: CacheResult | None = None
    client_cache_control = request.headers.get("cache-control", "").lower()

    if (
        cache_lookup is not None
        and "no-cache" not in client_cache_control
        and "no-store" not in client_cache_control
    ):
        result = await cache_lookup.check(request_data, tenant_id)

        if result.hit:
            logger.info("Serving cache HIT for tenant=%s", tenant_id)
            hit_headers = {"X-Cache": "HIT"}
            if routing_result.was_routed:
                hit_headers["X-Cached-Model"] = routing_result.routed_model

            if request_data.stream:
                return StreamingResponse(
                    replay_sse_stream(result.cached_response),
                    media_type="text/event-stream",
                    headers=hit_headers,
                )
            else:
                return replay_json_response(
                    result.cached_response,
                    extra_headers=hit_headers,
                )

    # ------------------------------------------------------------------ #
    #  2.  Cache MISS or BYPASS — forward to upstream                     #
    # ------------------------------------------------------------------ #
    client_bypassed = (
        "no-cache" in client_cache_control or "no-store" in client_cache_control
    )
    x_cache_header = (
        "MISS" if cache_lookup is not None and not client_bypassed else "BYPASS"
    )

    # Build extra headers for the miss/bypass response
    extra_headers: dict[str, str] = {"X-Cache": x_cache_header}
    if routing_result.was_routed:
        extra_headers["X-Routed-Model"] = routing_result.routed_model

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
            headers=extra_headers,
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
            headers=extra_headers,
        )
