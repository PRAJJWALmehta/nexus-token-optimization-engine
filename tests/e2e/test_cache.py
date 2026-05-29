"""End-to-End tests for semantic caching against a real Redis instance.

These tests correspond to the scenarios outlined in docs/TESTING_GUIDE.md.
They use the real Redis Stack (expected on localhost:6379) and real sentence
transformers, but mock the upstream OpenAI provider to avoid needing an API key.

Requires:
    - Redis Stack running (e.g. via `docker compose up -d`)
    - CACHE_ENABLED=true in the environment (default)
"""

import json
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import settings

# ---------------------------------------------------------------------------
# Test Data
# ---------------------------------------------------------------------------

_SYSTEM_MSG = {"role": "system", "content": "You are a helpful assistant."}
_USER_MSG = {"role": "user", "content": "Explain quantum computing in one simple sentence."}

_MOCK_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "gpt-4o",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "This is a mock response."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
).encode()

async def _fake_stream(request) -> AsyncIterator[bytes]:
    yield _MOCK_RESPONSE

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def app():
    """Create the FastAPI app instance."""
    # Ensure cache is enabled so lifespan connects to Redis and Embedder
    settings.cache_enabled = True
    settings.redis_url = "redis://localhost:6379"
    return create_app()

@pytest.fixture
def client(app):
    """TestClient that runs lifespan events on entering the context block."""
    with TestClient(app) as c:
        # Flush the real Redis DB to ensure clean state before each test
        # We use a fresh sync client to avoid messing with async event loops.
        import redis
        try:
            r = redis.Redis.from_url(settings.redis_url)
            keys = r.keys("cache:*")
            if keys:
                r.delete(*keys)
        except redis.ConnectionError:
            pass # Handle gracefully if Redis is down (e.g. Scenario 6)
        
        # Patch the upstream provider to return our mock response
        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            side_effect=_fake_stream,
        ):
            yield c

# ---------------------------------------------------------------------------
# Tests (Mapping to TESTING_GUIDE.md scenarios)
# ---------------------------------------------------------------------------

def test_scenario_1_and_2_miss_then_hit(client):
    """Scenario 1 & 2: First request is a MISS, identical second request is a HIT."""
    payload = {"model": "gpt-4o", "messages": [_SYSTEM_MSG, _USER_MSG]}
    
    # First request: MISS
    resp1 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp1.status_code == 200
    assert resp1.headers.get("x-cache") == "MISS"
    assert resp1.json()["choices"][0]["message"]["content"] == "This is a mock response."

    # Give the background task a tiny moment to write to Redis
    import time
    time.sleep(0.5)

    # Second request: HIT
    resp2 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("x-cache") == "HIT"
    assert resp2.json()["choices"][0]["message"]["content"] == "This is a mock response."

def test_scenario_3_temperature_bucketing(client):
    """Scenario 3: Temperature bucketing (0.70 and 0.74 hit the same bucket)."""
    payload_1 = {"model": "gpt-4o", "temperature": 0.70, "messages": [_USER_MSG]}
    payload_2 = {"model": "gpt-4o", "temperature": 0.74, "messages": [_USER_MSG]}
    
    # First request with temp 0.70
    resp1 = client.post(
        "/v1/chat/completions",
        json=payload_1,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp1.headers.get("x-cache") == "MISS"
    
    import time
    time.sleep(0.5)

    # Second request with temp 0.74 (should hit the 0.7 bucket)
    resp2 = client.post(
        "/v1/chat/completions",
        json=payload_2,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp2.headers.get("x-cache") == "HIT"

def test_scenario_4_tenant_isolation(client):
    """Scenario 4: Ensure a cache entry for one tenant cannot be accessed by another."""
    payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "Tell me a joke about a tomato."}]}
    
    # Tenant A requests
    respA = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer tenantA_secret"},
    )
    assert respA.headers.get("x-cache") == "MISS"
    
    import time
    time.sleep(0.5)

    # Tenant B requests identical prompt
    respB = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer tenantB_secret"},
    )
    assert respB.headers.get("x-cache") == "MISS"

def test_scenario_5_cache_bypass():
    """Scenario 5: Test that the cache can be bypassed via configuration."""
    # We create a new app specifically for this test with caching disabled
    with patch("src.config.settings.cache_enabled", False):
        app = create_app()
        with TestClient(app) as c:
            with patch(
                "src.routers.chat.OpenAIProviderAdapter.stream_completions",
                side_effect=_fake_stream,
            ):
                payload = {"model": "gpt-4o", "messages": [_USER_MSG]}
                resp = c.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer test_tenant"},
                )
                assert resp.status_code == 200
                assert resp.headers.get("x-cache") == "BYPASS"

def test_scenario_6_graceful_degradation():
    """Scenario 6: Test that the gateway continues to serve traffic if Redis fails."""
    # We patch the redis_url to something invalid to simulate downtime
    with patch("src.config.settings.redis_url", "redis://invalid-host:6379"):
        app = create_app()
        # The lifespan will log a warning and disable the store
        with TestClient(app) as c:
            with patch(
                "src.routers.chat.OpenAIProviderAdapter.stream_completions",
                side_effect=_fake_stream,
            ):
                payload = {"model": "gpt-4o", "messages": [_USER_MSG]}
                resp = c.post(
                    "/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer test_tenant"},
                )
                assert resp.status_code == 200
                assert resp.headers.get("x-cache") == "BYPASS"

def test_scenario_7_client_cache_bypass(client):
    """Scenario 7: Client explicitly requests cache bypass using Cache-Control: no-cache."""
    payload = {"model": "gpt-4o", "messages": [_USER_MSG]}

    # First request: normal request, should be a MISS
    resp1 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp1.headers.get("x-cache") == "MISS"

    import time
    time.sleep(0.5)

    # Second request: same payload, but client sends no-cache.
    # Gateway should bypass cache lookup and return BYPASS.
    resp2 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={
            "Authorization": "Bearer test_tenant",
            "Cache-Control": "no-cache"
        },
    )
    assert resp2.headers.get("x-cache") == "BYPASS"

    # Third request: normal request without no-cache.
    # Gateway should still have the original cache entry, so it's a HIT.
    resp3 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp3.headers.get("x-cache") == "HIT"
