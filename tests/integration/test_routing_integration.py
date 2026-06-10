"""Integration tests for dynamic model routing.

Tests the full request pipeline through the FastAPI app:
- "Format this JSON" with model="auto" → routes to Sonnet (low complexity)
- "Refactor this architecture" with model="auto" → routes to Opus (high complexity)
- Explicit model name bypasses routing entirely
- X-Routed-Model header on cache MISS
- X-Cached-Model header on cache HIT
- Routing disabled + model="auto" → 400 Bad Request
- Routing disabled + explicit model → passthrough (200)

Run with:
    pytest tests/integration/test_routing_integration.py -v
"""

from __future__ import annotations

import json
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.cache.lookup import CacheLookup, CacheResult
from src.config import Settings
from src.routing.router import ModelRouter, RoutingResult

# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

_NON_STREAM_RESPONSE = json.dumps(
    {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "claude-sonnet-4-20250514",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Done."},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
).encode()

_SYSTEM_MSG = {"role": "system", "content": "You are a helpful assistant."}


# ---------------------------------------------------------------------------
# App factory helpers
# ---------------------------------------------------------------------------


def _make_app():
    """Create a FastAPI app with cache disabled (to isolate routing tests)."""
    from src.app import create_app

    with patch("src.config.settings.cache_enabled", False):
        return create_app()


def _make_settings(**overrides) -> Settings:
    """Build a Settings instance with routing overrides applied."""
    base = {
        "upstream_api_url": "http://localhost:8001/v1/chat/completions",
        "upstream_api_key": "test-key",
        "routing_enabled": True,
        "routing_trigger_model": "auto",
        "routing_token_threshold": 2000,
        "routing_low_model": "claude-sonnet-4-20250514",
        "routing_high_model": "claude-opus-4-0520",
        "routing_complexity_keywords": "refactor,architect,design",
    }
    base.update(overrides)
    return Settings(**base)


async def _fake_stream(req) -> AsyncIterator[bytes]:
    yield _NON_STREAM_RESPONSE


def _patch_provider():
    return patch(
        "src.routers.chat.OpenAIProviderAdapter.stream_completions",
        return_value=_fake_stream(None),
    )


class _StubCacheLookup:
    """Minimal CacheLookup stub that supports the app.py shutdown path.

    MagicMock(spec=CacheLookup) doesn't have ``_store`` so the lifespan
    shutdown in app.py crashes.  This stub returns a controlled result
    from ``check()`` and does nothing on shutdown.
    """

    def __init__(self, hit: bool, response: bytes):
        from src.cache.lookup import CacheResult
        self._result = CacheResult(hit=hit, cached_response=response, key=None)
        # Stub _store so app.py lifespan can call _store.close()
        self._store = _StubStore()

    async def check(self, request_data, tenant_id):
        return self._result


class _StubStore:
    """Minimal store stub — close() does nothing."""
    disabled: bool = False

    async def close(self):
        pass


# ---------------------------------------------------------------------------
# 1. "Format this JSON" → Sonnet (low complexity)
# ---------------------------------------------------------------------------


class TestLowComplexityRouting:
    def test_format_json_routes_to_sonnet(self):
        """'Format this JSON' → low complexity → Sonnet."""
        app = _make_app()

        # Capture what model is forwarded upstream by inspecting the resolved request
        captured_model: list[str] = []

        async def _capturing_stream(req) -> AsyncIterator[bytes]:
            captured_model.append(req.model)
            yield _NON_STREAM_RESPONSE

        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            side_effect=_capturing_stream,
        ):
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [
                            _SYSTEM_MSG,
                            {"role": "user", "content": "Format this JSON: {}"},
                        ],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert len(captured_model) == 1
        assert captured_model[0] == "claude-sonnet-4-20250514", (
            f"Expected Sonnet for low-complexity prompt, got: {captured_model[0]}"
        )

    def test_format_json_has_routed_model_header(self):
        """Low-complexity routed response includes X-Routed-Model header."""
        app = _make_app()

        with _patch_provider():
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [{"role": "user", "content": "Format this JSON: {}"}],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert resp.headers.get("x-routed-model") == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# 2. "Refactor this architecture" → Opus (high complexity)
# ---------------------------------------------------------------------------


class TestHighComplexityRouting:
    def test_refactor_routes_to_opus(self):
        """'Refactor this architecture' → high complexity → Opus."""
        app = _make_app()

        captured_model: list[str] = []

        async def _capturing_stream(req) -> AsyncIterator[bytes]:
            captured_model.append(req.model)
            yield _NON_STREAM_RESPONSE

        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            side_effect=_capturing_stream,
        ):
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [
                            {"role": "user", "content": "Refactor this architecture for scalability"},
                        ],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert len(captured_model) == 1
        assert captured_model[0] == "claude-opus-4-0520", (
            f"Expected Opus for high-complexity prompt, got: {captured_model[0]}"
        )

    def test_refactor_has_routed_model_header(self):
        """High-complexity routed response includes X-Routed-Model header."""
        app = _make_app()

        with _patch_provider():
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [
                            {"role": "user", "content": "Refactor this architecture"},
                        ],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert resp.headers.get("x-routed-model") == "claude-opus-4-0520"


# ---------------------------------------------------------------------------
# 3. Explicit model bypasses routing
# ---------------------------------------------------------------------------


class TestExplicitModelBypass:
    def test_explicit_model_not_rerouted(self):
        """Explicit model name is forwarded unchanged; no routing header."""
        app = _make_app()

        captured_model: list[str] = []

        async def _capturing_stream(req) -> AsyncIterator[bytes]:
            captured_model.append(req.model)
            yield _NON_STREAM_RESPONSE

        with patch(
            "src.routers.chat.OpenAIProviderAdapter.stream_completions",
            side_effect=_capturing_stream,
        ):
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "gpt-4o",
                        "messages": [{"role": "user", "content": "Refactor everything"}],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )

        assert resp.status_code == 200
        assert captured_model[0] == "gpt-4o", (
            "Explicit model must NOT be changed by the router"
        )
        assert "x-routed-model" not in resp.headers
        assert "x-cached-model" not in resp.headers


# ---------------------------------------------------------------------------
# 4. X-Cached-Model header on cache HIT
# ---------------------------------------------------------------------------


class TestCachedModelHeader:
    def test_cached_model_header_on_hit(self):
        """Cache HIT on a previously routed request returns X-Cached-Model."""
        app = _make_app()

        # Use stub CacheLookup (not MagicMock) so lifespan shutdown works
        stub_lookup = _StubCacheLookup(hit=True, response=_NON_STREAM_RESPONSE)

        # Override get_model_router to return a router that reports routing
        mock_router = MagicMock(spec=ModelRouter)
        mock_router.resolve.return_value = RoutingResult(routed_model="claude-sonnet-4-20250514")

        from src.routers.chat import get_model_router
        app.dependency_overrides[get_model_router] = lambda: mock_router

        try:
            with TestClient(app) as client:
                app.state.cache_lookup = stub_lookup
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [{"role": "user", "content": "Format this JSON: {}"}],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.headers.get("x-cache") == "HIT"
        assert resp.headers.get("x-cached-model") == "claude-sonnet-4-20250514"
        assert "x-routed-model" not in resp.headers


# ---------------------------------------------------------------------------
# 5. Routing disabled
# ---------------------------------------------------------------------------


class TestRoutingDisabled:
    def _make_disabled_router(self) -> ModelRouter:
        """Build a real ModelRouter with routing_enabled=False."""
        disabled_settings = _make_settings(routing_enabled=False)
        return ModelRouter(settings=disabled_settings)

    def test_routing_disabled_auto_model_returns_400(self):
        """Routing disabled + model='auto' → 400 Bad Request."""
        app = _make_app()
        disabled_router = self._make_disabled_router()

        from src.routers.chat import get_model_router
        app.dependency_overrides[get_model_router] = lambda: disabled_router

        try:
            with TestClient(app) as client:
                app.state.cache_lookup = None
                resp = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "auto",
                        "messages": [{"role": "user", "content": "Hello"}],
                    },
                    headers={"Authorization": "Bearer testkey"},
                )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 400
        body = resp.json()
        assert "disabled" in body.get("error", {}).get("message", "").lower()

    def test_routing_disabled_explicit_model_passes_through(self):
        """Routing disabled + explicit model → passes through normally (200)."""
        app = _make_app()
        disabled_router = self._make_disabled_router()

        from src.routers.chat import get_model_router
        app.dependency_overrides[get_model_router] = lambda: disabled_router

        try:
            with _patch_provider():
                with TestClient(app) as client:
                    app.state.cache_lookup = None
                    resp = client.post(
                        "/v1/chat/completions",
                        json={
                            "model": "gpt-4o",
                            "messages": [{"role": "user", "content": "Hello"}],
                        },
                        headers={"Authorization": "Bearer testkey"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert "x-routed-model" not in resp.headers
