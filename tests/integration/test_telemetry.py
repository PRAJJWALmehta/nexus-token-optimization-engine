from __future__ import annotations

import json
import pytest
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.app import create_app
from src.cache.store import CacheEntry
from src.telemetry import (
    cache_hits_total,
    cache_misses_total,
    tokens_saved_total,
    gateway_latency_seconds,
    provider_latency_seconds,
    requests_per_model,
)

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


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear metric values before each test to ensure predictable increments."""
    cache_hits_total.clear()
    cache_misses_total.clear()
    tokens_saved_total.clear()
    
    gateway_latency_seconds._sum.set(0.0)
    for b in gateway_latency_seconds._buckets:
        b.set(0.0)
        
    provider_latency_seconds.clear()
    requests_per_model.clear()
    yield


def test_telemetry_metrics_exposed():
    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "cache_hits_total" in resp.text
        assert "cache_misses_total" in resp.text
        assert "tokens_saved_total" in resp.text
        assert "gateway_latency_seconds" in resp.text
        assert "provider_latency_seconds" in resp.text
        assert "requests_per_model" in resp.text


@pytest.mark.asyncio
async def test_telemetry_flow_on_cache_miss_and_hit():
    from tests.integration.test_cache_integration import _disabled_store, _make_lookup, embedder
    
    # We construct a real embedding engine, but a store with mocked ANN search
    store = _disabled_store()
    store.disabled = False
    
    # First search gets None (MISS), second search gets the entry (HIT)
    cached_entry = CacheEntry(
        redis_key="cache:fake-uuid",
        response=_NON_STREAM_RESPONSE,
        ctx_hash="dummy",  # will be overwritten to match the request context
        stream=False,
        score=0.99,
    )
    
    call_count = {"n": 0}
    
    async def _search_side_effect(key_arg, vector_arg):
        call_count["n"] += 1
        print(f"\n--- _search_side_effect called: n={call_count['n']} ---")
        if call_count["n"] == 1:
            return None
        cached_entry.ctx_hash = key_arg.ctx_hash
        return cached_entry

    store.search = AsyncMock(side_effect=_search_side_effect)
    store.store = AsyncMock(return_value=None)
    
    from src.cache.embedder import EmbeddingEngine
    real_embedder = EmbeddingEngine()
    lookup = _make_lookup(real_embedder, store)
    
    app = create_app()

    async def _fake_stream(req) -> AsyncIterator[bytes]:
        yield _NON_STREAM_RESPONSE

    with patch(
        "src.routers.chat.OpenAIProviderAdapter.stream_completions",
        side_effect=lambda req: _fake_stream(req),
    ):
        with TestClient(app) as client:
            app.state.cache_lookup = lookup
            # 1. Miss Request
            resp1 = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [_SYSTEM_MSG, _USER_MSG], "temperature": 0.7},
                headers={"Authorization": "Bearer testkey"},
            )
            assert resp1.status_code == 200
            assert resp1.headers.get("x-cache") == "MISS"
            
            from prometheus_client import REGISTRY
            assert REGISTRY.get_sample_value('cache_misses_total', {'model': 'gpt-4o'}) == 1.0
            assert REGISTRY.get_sample_value('cache_hits_total', {'model': 'gpt-4o'}) is None
            assert REGISTRY.get_sample_value('provider_latency_seconds_count', {'model': 'gpt-4o', 'provider': 'openai'}) == 1.0
            assert REGISTRY.get_sample_value('gateway_latency_seconds_count') == 1.0
            assert REGISTRY.get_sample_value('requests_per_model', {'model': 'gpt-4o'}) == 1.0

            # 2. Hit Request
            resp2 = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4o", "messages": [_SYSTEM_MSG, _USER_MSG], "temperature": 0.7},
                headers={"Authorization": "Bearer testkey"},
            )
            assert resp2.status_code == 200
            assert resp2.headers.get("x-cache") == "HIT"
            
            assert REGISTRY.get_sample_value('cache_misses_total', {'model': 'gpt-4o'}) == 1.0
            assert REGISTRY.get_sample_value('cache_hits_total', {'model': 'gpt-4o'}) == 1.0
            assert REGISTRY.get_sample_value('provider_latency_seconds_count', {'model': 'gpt-4o', 'provider': 'openai'}) == 1.0
            assert REGISTRY.get_sample_value('gateway_latency_seconds_count') == 2.0
            assert REGISTRY.get_sample_value('requests_per_model', {'model': 'gpt-4o'}) == 2.0
            
            tokens_saved_val = REGISTRY.get_sample_value('tokens_saved_total', {'model': 'gpt-4o', 'source': 'caching'})
            print(f"\n--- tokens_saved_total val: {tokens_saved_val} ---")
            assert tokens_saved_val == 15.0
