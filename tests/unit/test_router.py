"""Unit tests for ModelRouter.

Covers all spec scenarios:
- Trigger model activates routing
- Non-trigger model bypasses routing (result.routed_model is None)
- Low complexity → Sonnet (low model)
- High complexity → Opus (high model)
- Routing disabled + trigger model → RoutingDisabledError (400)
- Routing disabled + non-trigger model → passthrough unchanged
- Custom model mappings via settings
- INFO-level structured log on routing decision
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from src.config import Settings
from src.models.chat import ChatCompletionRequest, ChatMessage
from src.routing.classifier import ComplexityClassifier, ComplexityLevel, ComplexityResult
from src.routing.router import ModelRouter, RoutingDisabledError, RoutingResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(model: str, user_content: str = "Hello") -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=[ChatMessage(role="user", content=user_content)],
    )


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


def _low_classifier() -> ComplexityClassifier:
    """A mock-like classifier that always returns LOW."""
    clf = MagicMock(spec=ComplexityClassifier)
    clf.classify.return_value = ComplexityResult(
        level=ComplexityLevel.LOW, tokens_est=10, keyword_match=None
    )
    return clf


def _high_classifier() -> ComplexityClassifier:
    """A mock-like classifier that always returns HIGH."""
    clf = MagicMock(spec=ComplexityClassifier)
    clf.classify.return_value = ComplexityResult(
        level=ComplexityLevel.HIGH, tokens_est=500, keyword_match="refactor"
    )
    return clf


# ---------------------------------------------------------------------------
# Trigger model activation
# ---------------------------------------------------------------------------


class TestTriggerModelActivation:
    def test_trigger_model_activates_routing(self):
        """model='auto' triggers routing and mutates request.model."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        result = router.resolve(req)

        assert result.was_routed is True
        assert result.routed_model == "claude-sonnet-4-20250514"
        assert req.model == "claude-sonnet-4-20250514", "Request model must be mutated in place"

    def test_non_trigger_model_bypasses(self):
        """Explicit model names bypass routing entirely."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("gpt-4o")

        result = router.resolve(req)

        assert result.was_routed is False
        assert result.routed_model is None
        assert req.model == "gpt-4o", "Non-trigger request model must not be changed"

    def test_custom_trigger_model_name(self):
        """Custom trigger model name activates routing correctly."""
        settings = _make_settings(routing_trigger_model="nexus-auto")
        router = ModelRouter(settings=settings, classifier=_low_classifier())

        # "auto" should NOT trigger routing when trigger is "nexus-auto"
        req_auto = _make_request("auto")
        result_auto = router.resolve(req_auto)
        assert result_auto.was_routed is False

        # "nexus-auto" SHOULD trigger routing
        req_nexus = _make_request("nexus-auto")
        result_nexus = router.resolve(req_nexus)
        assert result_nexus.was_routed is True


# ---------------------------------------------------------------------------
# Model mapping
# ---------------------------------------------------------------------------


class TestModelMapping:
    def test_low_complexity_routes_to_sonnet(self):
        """LOW complexity → routing_low_model (Sonnet)."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        result = router.resolve(req)

        assert result.routed_model == "claude-sonnet-4-20250514"
        assert req.model == "claude-sonnet-4-20250514"

    def test_high_complexity_routes_to_opus(self):
        """HIGH complexity → routing_high_model (Opus)."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_high_classifier())
        req = _make_request("auto")

        result = router.resolve(req)

        assert result.routed_model == "claude-opus-4-0520"
        assert req.model == "claude-opus-4-0520"

    def test_custom_low_model_mapping(self):
        """Custom routing_low_model is used for low-complexity requests."""
        settings = _make_settings(routing_low_model="gpt-4o-mini")
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        result = router.resolve(req)

        assert result.routed_model == "gpt-4o-mini"

    def test_custom_high_model_mapping(self):
        """Custom routing_high_model is used for high-complexity requests."""
        settings = _make_settings(routing_high_model="gpt-4o")
        router = ModelRouter(settings=settings, classifier=_high_classifier())
        req = _make_request("auto")

        result = router.resolve(req)

        assert result.routed_model == "gpt-4o"


# ---------------------------------------------------------------------------
# Routing disabled
# ---------------------------------------------------------------------------


class TestRoutingDisabled:
    def test_disabled_plus_trigger_raises_error(self):
        """Routing disabled + trigger model → RoutingDisabledError."""
        settings = _make_settings(routing_enabled=False)
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        with pytest.raises(RoutingDisabledError) as exc_info:
            router.resolve(req)

        assert "disabled" in str(exc_info.value).lower()

    def test_disabled_plus_non_trigger_passes_through(self):
        """Routing disabled + non-trigger model → passthrough unchanged."""
        settings = _make_settings(routing_enabled=False)
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("gpt-4o")

        result = router.resolve(req)

        assert result.was_routed is False
        assert req.model == "gpt-4o", "Non-trigger model must not be changed when routing disabled"

    def test_disabled_trigger_model_not_mutated(self):
        """Trigger model is NOT mutated when routing is disabled (error raised before mutation)."""
        settings = _make_settings(routing_enabled=False)
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        with pytest.raises(RoutingDisabledError):
            router.resolve(req)

        # model must remain unchanged (error raised before mutation occurs)
        assert req.model == "auto"


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestRoutingLogging:
    def test_routing_decision_logged_at_info(self, caplog):
        """Routing decisions are logged at INFO level with structured fields."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("auto")

        with caplog.at_level(logging.INFO, logger="src.routing.router"):
            router.resolve(req)

        assert len(caplog.records) >= 1
        record = caplog.records[0]
        assert record.levelno == logging.INFO
        # Check key structured fields are present in the log message
        assert "auto" in record.getMessage()
        assert "claude-sonnet-4-20250514" in record.getMessage()

    def test_non_routing_does_not_log(self, caplog):
        """Non-trigger requests do NOT produce a routing decision log."""
        settings = _make_settings()
        router = ModelRouter(settings=settings, classifier=_low_classifier())
        req = _make_request("gpt-4o")

        with caplog.at_level(logging.INFO, logger="src.routing.router"):
            router.resolve(req)

        routing_logs = [r for r in caplog.records if "Routing decision" in r.getMessage()]
        assert len(routing_logs) == 0


# ---------------------------------------------------------------------------
# Settings-driven classifier construction
# ---------------------------------------------------------------------------


class TestClassifierConstruction:
    def test_router_builds_classifier_from_settings(self):
        """ModelRouter constructs a classifier from settings when none provided."""
        settings = _make_settings(
            routing_token_threshold=500,
            routing_complexity_keywords="migrate,overhaul",
        )
        router = ModelRouter(settings=settings)
        # Send a request with a custom keyword that should trigger HIGH
        req = _make_request("auto", "Please migrate the database")
        result = router.resolve(req)
        assert result.routed_model == "claude-opus-4-0520"  # HIGH → Opus
