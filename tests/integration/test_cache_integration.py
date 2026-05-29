"""Integration tests for semantic caching.

These tests use mocked store operations and a stub upstream provider to verify
the end-to-end cache hit / miss / bypass / degradation paths without requiring
a real Redis or OpenAI API.

Run with:
    pytest tests/test_cache_integration.py -v
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from src.cache.embedder import EmbeddingEngine
from src.cache.key_builder import CacheKeyBuilder
from src.cache.lookup import CacheLookup, CacheResult
from src.cache.store import CacheEntry, RedisCacheStore

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

_SYSTEM_MSG = {"role": "system", "content": "You are a helpful assistant."}
_USER_MSG = {"role": "user", "content": "What is the capital of France?"}

_NON_STREAM_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Paris."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
    }
).encode()

_SSE_RESPONSE = (
    b'data: {"id":"chatcmpl-x","object":"chat.completion.chunk","created":1700000000,'
    b'"model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant","content":"Paris"},'
    b'"finish_reason":null}]}\n\n'
    b"data: [DONE]\n\n"
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def embedder() -> EmbeddingEngine:
    """Real embedding engine — loaded once for the whole module."""
    return EmbeddingEngine()


def _disabled_store() -> RedisCacheStore:
    """Build a RedisCacheStore that is pre-disabled (simulates Redis down)."""
    store = RedisCacheStore.__new__(RedisCacheStore)
    store.disabled = True
    store._client = None
    store._threshold = 0.95
    store._ttl = 60
    store._max_bytes = 524288
    return store


def _make_lookup(embedder: EmbeddingEngine, store: RedisCacheStore) -> CacheLookup:
    return CacheLookup(embedder=embedder, store=store)


def _make_app():
    """Create a fresh FastAPI app (lifespan skipped via cache_enabled=False)."""
    from src.app import create_app

    with patch("src.config.settings.cache_enabled", False):
        return create_app()


# ---------------------------------------------------------------------------
# 10.3  Cache BYPASS (cache_lookup = None / disabled)
# ---------------------------------------------------------------------------


class TestCacheBypass:
    """Task 10.3: X-Cache: BYPASS when caching is off."""

    def test_bypass_header_when_cache_disabled(self):
        """X-Cache: BYPASS when cache_lookup is None on app.state."""
        from fastapi.testclient import TestClient

        app = _make_app()

        async def _fake_stream(req) -> AsyncIterator[bytes]:
            yield _NON_STREAM_RESPONSE

        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            return_value=_fake_stream(None),
        ):
            with TestClient(app) as client:
                # Ensure cache_lookup is None after lifespan (cache disabled)
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [_SYSTEM_MSG, _USER_MSG]},
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert resp.headers.get("x-cache") == "BYPASS", (
            f"Expected X-Cache: BYPASS, got: {resp.headers.get('x-cache')!r}"
        )


# ---------------------------------------------------------------------------
# 10.4  Graceful degradation (Redis unavailable)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Task 10.4: Requests succeed even when Redis is down."""

    def test_requests_succeed_when_redis_unavailable(self, embedder: EmbeddingEngine):
        """Gateway proxies requests transparently when Redis store is disabled."""
        from fastapi.testclient import TestClient

        store = _disabled_store()
        lookup = _make_lookup(embedder, store)
        app = _make_app()

        async def _fake_stream(req) -> AsyncIterator[bytes]:
            yield _NON_STREAM_RESPONSE

        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            return_value=_fake_stream(None),
        ):
            with TestClient(app) as client:
                # Inject lookup AFTER lifespan startup so it is not overwritten
                app.state.cache_lookup = lookup
                resp = client.post(
                    "/v1/chat/completions",
                    json={"model": "gpt-4o", "messages": [_SYSTEM_MSG, _USER_MSG]},
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        # Disabled store → CacheLookup.check returns MISS → X-Cache: MISS
        assert resp.headers.get("x-cache") == "MISS", (
            f"Expected X-Cache: MISS, got: {resp.headers.get('x-cache')!r}"
        )


# ---------------------------------------------------------------------------
# 10.1  Same prompt twice → second response is cache HIT
# ---------------------------------------------------------------------------


class TestCacheHit:
    """Task 10.1: Second identical request returns cache HIT."""

    @pytest.fixture
    def store_with_mock_ops(self) -> RedisCacheStore:
        """A store whose search/store methods are async mocks.

        search() first returns None (MISS), then on second call returns a
        pre-built CacheEntry (HIT) — simulating what Redis would do after
        a store() call.
        """
        store = _disabled_store()
        # Enable the store so CacheLookup doesn't short-circuit
        store.disabled = False
        return store

    async def test_same_prompt_twice_hits_cache(
        self, embedder: EmbeddingEngine, store_with_mock_ops: RedisCacheStore
    ):
        """After a MISS + store(), the second identical request must be a HIT."""
        from src.models.chat import ChatCompletionRequest, ChatMessage

        request = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(**_SYSTEM_MSG), ChatMessage(**_USER_MSG)],
            temperature=0.7,
        )
        tenant_id = "acme"

        key_builder = CacheKeyBuilder()
        key = key_builder.build(request, tenant_id)
        last_text = key_builder.last_user_text(request)
        embedding = embedder.encode(last_text)

        # Build the CacheEntry that the second search() call will return
        cached_entry = CacheEntry(
            redis_key="cache:fake-uuid",
            response=_NON_STREAM_RESPONSE,
            ctx_hash=key.ctx_hash,  # must match for HIT
            stream=False,
            score=0.99,
        )

        call_count = {"n": 0}

        async def _search_side_effect(key_arg, vector_arg):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # first call → MISS
            return cached_entry  # subsequent calls → HIT

        store = store_with_mock_ops
        store.search = AsyncMock(side_effect=_search_side_effect)
        store.store = AsyncMock(return_value=None)

        lookup = CacheLookup(embedder=embedder, store=store)

        # ---- First request: MISS ----
        result1 = await lookup.check(request, tenant_id)
        assert not result1.hit, "First request must be MISS"
        assert result1.key is not None

        # Store the response
        t0 = time.monotonic()
        await lookup.store(result1.key, request, _NON_STREAM_RESPONSE, stream=False)
        store_time = time.monotonic() - t0
        assert store_time < 0.5, "Store should be near-instant"
        store.store.assert_awaited_once()  # verify store was called

        # ---- Second request (same prompt): HIT ----
        t1 = time.monotonic()
        result2 = await lookup.check(request, tenant_id)
        lookup_time = time.monotonic() - t1

        assert result2.hit, "Second identical request must be a cache HIT"
        assert result2.cached_response == _NON_STREAM_RESPONSE
        assert lookup_time < 0.5, (
            f"Cache lookup took {lookup_time:.3f}s — expected near-zero latency"
        )


# ---------------------------------------------------------------------------
# 10.2  Different tenants → no cross-tenant cache hits
# ---------------------------------------------------------------------------


class TestTenantIsolation:
    """Task 10.2: Cache scoped strictly to tenant_id."""

    async def test_different_tenants_no_cross_cache_hit(self, embedder: EmbeddingEngine):
        """Data stored for tenant 'acme' must NOT surface for tenant 'beta'."""
        from src.models.chat import ChatCompletionRequest, ChatMessage

        request = ChatCompletionRequest(
            model="gpt-4o",
            messages=[ChatMessage(**_SYSTEM_MSG), ChatMessage(**_USER_MSG)],
            temperature=0.7,
        )

        key_builder = CacheKeyBuilder()
        key_acme = key_builder.build(request, "acme")
        key_beta = key_builder.build(request, "beta")

        # Tenant isolation is enforced at the KEY level: tenant_id differs
        assert key_acme.tenant_id == "acme"
        assert key_beta.tenant_id == "beta"
        assert key_acme.tenant_id != key_beta.tenant_id

        # Set up store: only returns a HIT when searched with tenant "acme" key
        store = _disabled_store()
        store.disabled = False

        last_text = key_builder.last_user_text(request)
        embedding = embedder.encode(last_text)

        cached_entry = CacheEntry(
            redis_key="cache:fake-uuid",
            response=_NON_STREAM_RESPONSE,
            ctx_hash=key_acme.ctx_hash,
            stream=False,
            score=0.99,
        )

        async def _search_tenant_scoped(key_arg, vector_arg):
            # Simulate Redis tag filter: only match acme's tenant_id
            if key_arg.tenant_id == "acme":
                return cached_entry
            return None  # beta gets MISS — different RediSearch filter

        store.search = AsyncMock(side_effect=_search_tenant_scoped)
        store.store = AsyncMock(return_value=None)

        lookup = CacheLookup(embedder=embedder, store=store)

        # Store for acme
        await lookup.store(key_acme, request, _NON_STREAM_RESPONSE, stream=False)

        # Acme should HIT
        result_acme = await lookup.check(request, tenant_id="acme")
        assert result_acme.hit, "Tenant 'acme' should get a cache HIT"

        # Beta must MISS — different tenant, different RediSearch filter
        result_beta = await lookup.check(request, tenant_id="beta")
        assert not result_beta.hit, (
            "Tenant 'beta' MUST NOT receive a cache hit from tenant 'acme' data"
        )
