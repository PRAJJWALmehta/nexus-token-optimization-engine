"""Redis + RediSearch vector cache store.

Manages the lifecycle of cache entries in Redis:
- Creates and reuses a RediSearch HNSW vector index on startup.
- Persists cache entries (embedding vector + response bytes + metadata).
- Performs filtered approximate nearest-neighbor (ANN) queries.
- Enforces TTL and max response size.
- Degrades gracefully on connection failures.

Redis schema
------------
Each cached entry is stored as a Redis Hash at key ``cache:{uuid}`` with:

  ``embedding``        bytes    384-dim float32 vector (little-endian)
  ``response``         bytes    raw SSE bytes (streaming) or JSON bytes
  ``tenant_id``        str      tenant identifier
  ``sys_prompt_hash``  str      SHA-256 of system messages
  ``model``            str      model name
  ``temp_bucket``      int      bucketed temperature
  ``ctx_hash``         str      SHA-256 of conversation context
  ``stream``           str      "1" | "0" — whether response is SSE

RediSearch index: ``idx:cache``
  VECTOR field:  ``embedding`` HNSW 384-dim COSINE
  TAG fields:    ``tenant_id``, ``sys_prompt_hash``, ``model``
  NUMERIC field: ``temp_bucket``
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import numpy as np

from src.cache.key_builder import CacheKey

logger = logging.getLogger(__name__)

_INDEX_NAME = "idx:cache"
_KEY_PREFIX = "cache:"


class CacheEntry:
    """A cache search result returned by :meth:`RedisCacheStore.search`."""

    __slots__ = ("redis_key", "response", "ctx_hash", "stream", "score")

    def __init__(
        self,
        redis_key: str,
        response: bytes,
        ctx_hash: str,
        stream: bool,
        score: float,
    ) -> None:
        self.redis_key = redis_key
        self.response = response
        self.ctx_hash = ctx_hash
        self.stream = stream
        self.score = score  # cosine similarity (higher = more similar)


class RedisCacheStore:
    """Redis-backed vector store for cached LLM responses.

    Parameters
    ----------
    redis_url:
        Redis connection URL (e.g. ``redis://localhost:6379``).
    similarity_threshold:
        Minimum cosine similarity score to consider a result a HIT.
    cache_ttl:
        TTL in seconds for each cache entry.
    max_response_bytes:
        Maximum size in bytes for a response to be stored.
    """

    def __init__(
        self,
        redis_url: str,
        similarity_threshold: float = 0.95,
        cache_ttl: int = 3600,
        max_response_bytes: int = 524288,
    ) -> None:
        self._url = redis_url
        self._threshold = similarity_threshold
        self._ttl = cache_ttl
        self._max_bytes = max_response_bytes
        self._client = None
        self.disabled = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Connect to Redis and create the RediSearch index if needed.

        Sets ``self.disabled = True`` and logs a warning on failure so the
        gateway can continue operating without caching.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore

            self._client = aioredis.from_url(
                self._url,
                decode_responses=False,  # we handle bytes manually
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Verify connection
            await self._client.ping()
            # Create or reuse the vector index
            await self._create_index()
            logger.info("RedisCacheStore connected to %s", self._url)
        except Exception as exc:
            logger.warning(
                "RedisCacheStore: could not connect to Redis (%s) — caching disabled.",
                exc,
            )
            self.disabled = True

    async def close(self) -> None:
        """Close the Redis connection pool."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def store(
        self,
        key: CacheKey,
        embedding: np.ndarray,
        response: bytes,
        stream: bool,
    ) -> None:
        """Persist a cache entry to Redis.

        No-op if the store is disabled, Redis is unavailable, or the response
        exceeds the configured maximum size.

        Parameters
        ----------
        key:
            Composite cache key containing all metadata fields.
        embedding:
            384-dim float32 vector for the cached query.
        response:
            Raw response bytes (SSE or JSON).
        stream:
            True if *response* contains SSE chunks, False for JSON.
        """
        if self.disabled:
            return

        if len(response) > self._max_bytes:
            logger.warning(
                "Cache entry too large (%d bytes > %d) — skipping.",
                len(response),
                self._max_bytes,
            )
            return

        try:
            entry_id = str(uuid.uuid4())
            redis_key = f"{_KEY_PREFIX}{entry_id}"
            mapping = {
                b"embedding": embedding.astype(np.float32).tobytes(),
                b"response": response,
                b"tenant_id": key.tenant_id.encode(),
                b"sys_prompt_hash": key.sys_prompt_hash.encode(),
                b"model": key.model.encode(),
                b"temp_bucket": str(key.temp_bucket).encode(),
                b"ctx_hash": key.ctx_hash.encode(),
                b"stream": b"1" if stream else b"0",
            }
            pipe = self._client.pipeline(transaction=False)
            pipe.hset(redis_key, mapping=mapping)
            pipe.expire(redis_key, self._ttl)
            await pipe.execute()
        except Exception as exc:
            logger.warning("Cache store failed: %s", exc)

    async def search(
        self,
        key: CacheKey,
        query_vector: np.ndarray,
    ) -> Optional[CacheEntry]:
        """Search for the nearest cached entry matching the composite key.

        Performs a filtered ANN query scoped to the request's
        ``tenant_id``, ``sys_prompt_hash``, ``model``, and ``temp_bucket``.
        Returns the top-1 result if its cosine similarity meets the threshold.

        Parameters
        ----------
        key:
            Composite cache key for filtering.
        query_vector:
            384-dim float32 embedding of the last user message.

        Returns
        -------
        CacheEntry or None
            The best matching entry, or None on MISS or error.
        """
        if self.disabled:
            return None

        try:
            from redis.commands.search.query import Query  # type: ignore

            # Build the pre-filter expression:
            # @tenant_id:{<val>} @sys_prompt_hash:{<val>} @model:{<val>}
            # @temp_bucket:[<val> <val>]
            pre_filter = (
                f"@tenant_id:{{{_escape_tag(key.tenant_id)}}} "
                f"@sys_prompt_hash:{{{_escape_tag(key.sys_prompt_hash)}}} "
                f"@model:{{{_escape_tag(key.model)}}} "
                f"@temp_bucket:[{key.temp_bucket} {key.temp_bucket}]"
            )
            print(f"DEBUG pre_filter: {pre_filter}")

            query_bytes = query_vector.astype(np.float32).tobytes()
            knn_query = (
                Query(f"({pre_filter})=>[KNN 1 @embedding $vec AS __score]")
                .sort_by("__score", asc=True)  # lower distance = better
                .return_fields(
                    "__score", "response", "ctx_hash", "stream"
                )
                .dialect(2)
                .paging(0, 1)
            )

            results = await self._client.ft(_INDEX_NAME).search(
                knn_query, query_params={"vec": query_bytes}
            )

            if not results.docs:
                return None

            doc = results.docs[0]
            # RediSearch COSINE metric returns distance (0 = identical)
            distance = float(getattr(doc, "__score", 1.0))
            score = 1.0 - distance

            if score < self._threshold:
                return None

            return CacheEntry(
                redis_key=doc.id,
                response=_get_bytes_field(doc, "response"),
                ctx_hash=_get_str_field(doc, "ctx_hash"),
                stream=_get_str_field(doc, "stream") == "1",
                score=score,
            )

        except Exception as exc:
            logger.warning("Cache search failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _create_index(self) -> None:
        """Create the RediSearch HNSW vector index, or reuse if it exists."""
        try:
            from redis.commands.search.field import (  # type: ignore
                NumericField,
                TagField,
                VectorField,
            )
            from redis.commands.search.index_definition import (  # type: ignore
                IndexDefinition,
                IndexType,
            )

            schema = (
                TagField("tenant_id", as_name="tenant_id"),
                TagField("sys_prompt_hash", as_name="sys_prompt_hash"),
                TagField("model", as_name="model"),
                NumericField("temp_bucket", as_name="temp_bucket"),
                VectorField(
                    "embedding",
                    "HNSW",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": 384,
                        "DISTANCE_METRIC": "COSINE",
                    },
                    as_name="embedding",
                ),
            )
            definition = IndexDefinition(
                prefix=[_KEY_PREFIX], index_type=IndexType.HASH
            )
            await self._client.ft(_INDEX_NAME).create_index(
                schema, definition=definition
            )
            logger.info("RediSearch index '%s' created.", _INDEX_NAME)
        except Exception as exc:
            exc_str = str(exc)
            if "Index already exists" in exc_str or "already exist" in exc_str.lower():
                logger.debug("RediSearch index '%s' already exists — reusing.", _INDEX_NAME)
            else:
                raise


# ---------------------------------------------------------------------------
# Field helpers — redis-py returns bytes or str depending on decode_responses
# ---------------------------------------------------------------------------


def _get_bytes_field(doc, field: str) -> bytes:
    val = getattr(doc, field, b"")
    if isinstance(val, str):
        return val.encode("latin-1")
    return val or b""


def _get_str_field(doc, field: str) -> str:
    val = getattr(doc, field, "")
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return val or ""


def _escape_tag(value: str) -> str:
    """Escape special RediSearch tag characters in *value*."""
    # Characters that need escaping in RediSearch tag values
    special = r',.<>{}[]"\':;!@#$%^&*()-+=~'
    return "".join(f"\\{c}" if c in special else c for c in value)
