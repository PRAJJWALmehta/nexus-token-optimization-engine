"""FastAPI application factory.

Assembles the token-optimization gateway by wiring together the tenant
extraction middleware, chat and health routers, global exception handlers,
and — when caching is enabled — the embedding engine and Redis cache store.

Lifecycle
---------
*Startup*: Initialise :class:`~src.cache.embedder.EmbeddingEngine` and
           :class:`~src.cache.store.RedisCacheStore`, then create a
           :class:`~src.cache.lookup.CacheLookup` and store it on
           ``app.state.cache_lookup``.

*Shutdown*: Close the Redis connection pool.

When ``settings.cache_enabled`` is ``False``, or when either the embedding
model or Redis fails to initialise, ``app.state.cache_lookup`` is set to
``None`` so the chat router falls back to pass-through mode automatically.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config import settings
from src.exceptions import register_exception_handlers
from src.middleware.tenant import TenantExtractionMiddleware
from src.routers import chat, health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI lifespan context manager.

    Initialises shared services on startup and tears them down on shutdown.
    """
    # ------------------------------------------------------------------ #
    #  STARTUP                                                             #
    # ------------------------------------------------------------------ #
    app.state.cache_lookup = None  # default: disabled

    if settings.cache_enabled:
        try:
            from src.cache.embedder import EmbeddingEngine
            from src.cache.lookup import CacheLookup
            from src.cache.store import RedisCacheStore

            logger.info("Initialising embedding engine…")
            embedder = EmbeddingEngine()

            logger.info("Initialising Redis cache store at %s…", settings.redis_url)
            store = RedisCacheStore(
                redis_url=settings.redis_url,
                similarity_threshold=settings.cache_similarity_threshold,
                cache_ttl=settings.cache_ttl,
                max_response_bytes=settings.cache_max_response_bytes,
            )
            await store.initialize()

            if not embedder.disabled and not store.disabled:
                app.state.cache_lookup = CacheLookup(embedder=embedder, store=store)
                logger.info("Semantic caching enabled.")
            else:
                logger.warning(
                    "Semantic caching disabled due to init failure "
                    "(embedder.disabled=%s, store.disabled=%s).",
                    embedder.disabled,
                    store.disabled,
                )
                # Keep a reference so we can close Redis later
                app.state._cache_store = store  # type: ignore[attr-defined]

        except Exception as exc:
            logger.error("Cache initialisation failed: %s — running in pass-through mode.", exc)
    else:
        logger.info("Semantic caching disabled via CACHE_ENABLED=false.")
        store = None

    yield

    # ------------------------------------------------------------------ #
    #  SHUTDOWN                                                            #
    # ------------------------------------------------------------------ #
    cache_lookup = getattr(app.state, "cache_lookup", None)
    if cache_lookup is not None:
        await cache_lookup._store.close()
        logger.info("Redis connection pool closed.")
    else:
        # Might still have a store reference if embedding worked but Redis failed
        _store = getattr(app.state, "_cache_store", None)
        if _store is not None:
            await _store.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Nexus Token-Optimization Gateway",
        description="A transparent OpenAI-compatible reverse proxy for cost optimization.",
        version="0.1.0",
        lifespan=_lifespan,
    )

    # 1. Register middleware
    app.add_middleware(TenantExtractionMiddleware)

    # 2. Register exception handlers
    register_exception_handlers(app)

    # 3. Include routers
    app.include_router(health.router)
    app.include_router(chat.router)

    return app


# The application instance used by Uvicorn
app = create_app()
