"""Model router for dynamic model selection.

Intercepts :class:`~src.models.chat.ChatCompletionRequest` objects whose
``model`` field matches the configured *trigger name* (default ``"auto"``),
classifies their complexity, and resolves the model to a concrete upstream
model name by mutating the request in place.

Routing is **opt-in**: requests with any other model name pass through
unchanged.

When routing is globally disabled (``routing_enabled=False``) and a client
sends the trigger model name, the router raises
:class:`RoutingDisabledError` which the chat router translates into a
``400 Bad Request`` response.

Decision Logging
----------------
Every routing decision (trigger matched + model resolved) is logged at
INFO level with structured fields for pre-telemetry observability::

    Routing decision: model=auto → resolved=claude-sonnet-4-20250514,
    complexity=low, tokens_est=312, keyword_match=none
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.config import Settings, settings as _default_settings
from src.models.chat import ChatCompletionRequest
from src.routing.classifier import ComplexityClassifier, ComplexityLevel

logger = logging.getLogger(__name__)


class RoutingDisabledError(Exception):
    """Raised when routing is disabled and the trigger model is used.

    The chat router catches this and returns a 400 Bad Request.
    """


@dataclass
class RoutingResult:
    """Outcome of :meth:`ModelRouter.resolve`.

    Attributes
    ----------
    routed_model:
        The resolved concrete model name when routing was applied.
        ``None`` when the request was not routed (model didn't match trigger
        or routing is disabled for a non-trigger request).
    """

    routed_model: Optional[str]

    @property
    def was_routed(self) -> bool:
        """``True`` if routing was applied (request model was mutated)."""
        return self.routed_model is not None


class ModelRouter:
    """Resolves trigger-model requests to concrete models.

    Parameters
    ----------
    settings:
        Application settings.  Defaults to the module-level singleton.
    classifier:
        Pre-built classifier instance.  When ``None``, a default
        :class:`~src.routing.classifier.ComplexityClassifier` is constructed
        from settings.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        classifier: Optional[ComplexityClassifier] = None,
    ) -> None:
        self._settings = settings or _default_settings
        self._classifier = classifier or self._build_classifier()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(self, request: ChatCompletionRequest) -> RoutingResult:
        """Classify *request* and mutate its ``model`` field if applicable.

        Parameters
        ----------
        request:
            The incoming chat completion request (may be mutated in place).

        Returns
        -------
        RoutingResult
            ``routed_model`` is set to the resolved model name when routing
            was applied, ``None`` otherwise.

        Raises
        ------
        RoutingDisabledError
            When routing is disabled and the trigger model name is used.
        """
        s = self._settings
        original_model = request.model

        # Routing globally disabled
        if not s.routing_enabled:
            if original_model == s.routing_trigger_model:
                raise RoutingDisabledError(
                    "Dynamic routing is disabled; specify a concrete model name"
                )
            # Non-trigger model with routing disabled → pass through
            from src.telemetry import requests_per_model
            requests_per_model.labels(model=original_model).inc()
            return RoutingResult(routed_model=None)

        # Not the trigger model → bypass routing
        if original_model != s.routing_trigger_model:
            from src.telemetry import requests_per_model
            requests_per_model.labels(model=original_model).inc()
            return RoutingResult(routed_model=None)

        # Classify and resolve
        classification = self._classifier.classify(request)
        if classification.level == ComplexityLevel.HIGH:
            resolved = s.routing_high_model
        else:
            resolved = s.routing_low_model

        # Mutate in place
        request.model = resolved

        from src.telemetry import requests_per_model
        requests_per_model.labels(model=resolved).inc()

        logger.info(
            "Routing decision: model=%s → resolved=%s, complexity=%s, "
            "tokens_est=%d, keyword_match=%s",
            original_model,
            resolved,
            classification.level.value,
            classification.tokens_est,
            classification.keyword_match or "none",
        )

        return RoutingResult(routed_model=resolved)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_classifier(self) -> ComplexityClassifier:
        """Construct a :class:`ComplexityClassifier` from settings."""
        keywords = [
            kw.strip()
            for kw in self._settings.routing_complexity_keywords.split(",")
            if kw.strip()
        ]
        return ComplexityClassifier(
            token_threshold=self._settings.routing_token_threshold,
            keywords=keywords,
        )
