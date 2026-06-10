"""End-to-End tests for dynamic routing against a real Redis instance and mocked upstream.

Verifies:
- Routing model header (X-Routed-Model) on cache MISS.
- Cache HIT preserves and returns X-Cached-Model header.
- Routing disabled (ROUTING_ENABLED=false) returns 400 Bad Request.
"""

import json
import time
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.app import create_app
from src.config import settings

_USER_MSG = {"role": "user", "content": "Format this JSON: {\"key\": \"value\"}"}
_REFACTOR_MSG = {"role": "user", "content": "Please refactor this architecture for scaling."}

_MOCK_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 1700000000,
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

@pytest.fixture(scope="session")
def app():
    settings.cache_enabled = True
    settings.routing_enabled = True
    settings.redis_url = "redis://localhost:6379"
    return create_app()

@pytest.fixture
def client(app):
    with TestClient(app) as c:
        import redis
        try:
            r = redis.Redis.from_url(settings.redis_url)
            keys = r.keys("cache:*")
            if keys:
                r.delete(*keys)
        except redis.ConnectionError:
            pass
        
        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            side_effect=_fake_stream,
        ):
            yield c

def test_routing_e2e_miss_then_hit(client):
    # 1. First request is a cache MISS and is routed to Sonnet (low complexity)
    payload = {"model": "auto", "messages": [_USER_MSG]}
    resp1 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp1.status_code == 200
    assert resp1.headers.get("x-cache") == "MISS"
    assert resp1.headers.get("x-routed-model") == "claude-sonnet-4-20250514"
    assert "x-cached-model" not in resp1.headers

    # Give write-behind a tiny moment to write to Redis
    time.sleep(0.5)

    # 2. Second request is a cache HIT and returns X-Cached-Model
    resp2 = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp2.status_code == 200
    assert resp2.headers.get("x-cache") == "HIT"
    assert resp2.headers.get("x-cached-model") == "claude-sonnet-4-20250514"
    assert "x-routed-model" not in resp2.headers

def test_routing_e2e_high_complexity_routes_to_opus(client):
    payload = {"model": "auto", "messages": [_REFACTOR_MSG]}
    resp = client.post(
        "/v1/chat/completions",
        json=payload,
        headers={"Authorization": "Bearer test_tenant"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("x-cache") == "MISS"
    assert resp.headers.get("x-routed-model") == "claude-opus-4-0520"

def test_routing_e2e_disabled_returns_400():
    # We patch settings.routing_enabled to False
    with patch("src.config.settings.routing_enabled", False):
        app = create_app()
        with TestClient(app) as c:
            resp = c.post(
                "/v1/chat/completions",
                json={"model": "auto", "messages": [_USER_MSG]},
                headers={"Authorization": "Bearer test_tenant"},
            )
            assert resp.status_code == 400
            assert "disabled" in resp.json()["error"]["message"].lower()
