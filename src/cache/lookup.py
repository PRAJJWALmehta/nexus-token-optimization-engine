"""Cache lookup orchestrator.

Orchestrates the full semantic cache check flow:

  build key → embed last user message → ANN search → ctx_hash verify → HIT/MISS

Returns a :class:`CacheResult` dataclass so the router can act on hit/miss
without needing to know the internals of embedding or Redis.

Graceful degradation
--------------------
If the embedding engine is disabled or Redis is unavailable, :meth:`CacheLookup.check`
returns a MISS result (``hit=False``) without raising an exception.  This ensures
the gateway continues to proxy requests transparently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.cache.embedder import EmbeddingEngine
from src.cache.key_builder import CacheKey, CacheKeyBuilder
from src.cache.store import RedisCacheStore
from src.models.chat import ChatCompletionRequest

logger = logging.getLogger(__name__)


@dataclass
class CacheResult:
    """Result of a semantic cache lookup.

    Attributes
    ----------
    hit:
        True when a sufficiently similar cached response was found and the
        context hash matches.
    cached_response:
        The raw bytes of the cached response (SSE or JSON), or None on MISS.
    stream:
        True if *cached_response* is SSE bytes, False if it is JSON.
    key:
        The composite cache key computed for the request (always present).
    """

    hit: bool
    cached_response: Optional[bytes] = None
    stream: bool = False
    key: Optional[CacheKey] = None
    metadata: dict = field(default_factory=dict)


class CacheLookup:
    """Checks the semantic cache for a given chat completion request.

    Parameters
    ----------
    embedder:
        The shared :class:`EmbeddingEngine` instance.
    store:
        The shared :class:`RedisCacheStore` instance.
    key_builder:
        Stateless :class:`CacheKeyBuilder` (defaults to a new instance).
    """

    def __init__(
        self,
        embedder: EmbeddingEngine,
        store: RedisCacheStore,
        key_builder: Optional[CacheKeyBuilder] = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._key_builder = key_builder or CacheKeyBuilder()

    async def check(
        self, request: ChatCompletionRequest, tenant_id: str
    ) -> CacheResult:
        """Run the full cache lookup pipeline.

        1. Build composite cache key.
        2. Extract + embed last user message.
        3. ANN search with metadata filter.
        4. Verify ctx_hash on top result.

        Parameters
        ----------
        request:
            The validated chat completion request.
        tenant_id:
            The tenant extracted by the middleware.

        Returns
        -------
        CacheResult
            Always returns; never raises.
        """
        # Guard: degraded embedding engine → always MISS
        if self._embedder.disabled:
            logger.debug("CacheLookup: embedding engine disabled → MISS")
            return CacheResult(hit=False)

        # Guard: degraded Redis → always MISS
        if self._store.disabled:
            logger.debug("CacheLookup: Redis store disabled → MISS")
            return CacheResult(hit=False)

        try:
            # Step 1: build composite key
            key = self._key_builder.build(request, tenant_id)

            # Step 2: embed last user message
            last_user_text = self._key_builder.last_user_text(request)
            query_vector = self._embedder.encode(last_user_text)

            # Step 3: ANN search with metadata filter
            entry = await self._store.search(key, query_vector)
            if entry is None:
                return CacheResult(hit=False, key=key)

            # Step 4: context hash verification (second gate)
            if entry.ctx_hash != key.ctx_hash:
                logger.debug(
                    "CacheLookup: similarity match but ctx_hash mismatch → MISS "
                    "(score=%.4f)",
                    entry.score,
                )
                return CacheResult(hit=False, key=key)

            logger.info(
                "Cache HIT for tenant=%s model=%s score=%.4f",
                tenant_id,
                key.model,
                entry.score,
            )
            return CacheResult(
                hit=True,
                cached_response=entry.response,
                stream=entry.stream,
                key=key,
                metadata={"score": entry.score},
            )

        except Exception as exc:  # pragma: no cover
            logger.warning("CacheLookup.check() unexpected error: %s", exc)
            return CacheResult(hit=False)

    async def store(
        self,
        key: CacheKey,
        request: ChatCompletionRequest,
        response: bytes,
        stream: bool,
    ) -> None:
        """Persist a response to the cache after upstream delivery.

        Delegates to :meth:`RedisCacheStore.store`.  No-op if the store is
        disabled or the operation fails.
        """
        if self._store.disabled or self._embedder.disabled:
            return

        try:
            last_user_text = self._key_builder.last_user_text(request)
            embedding = self._embedder.encode(last_user_text)
            await self._store.store(key, embedding, response, stream)
        except Exception as exc:  # pragma: no cover
            logger.warning("CacheLookup.store() failed: %s", exc)
