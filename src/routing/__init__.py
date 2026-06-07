"""Dynamic routing package for Nexus Token-Optimization Gateway.

Provides heuristic complexity classification and model routing that
intercepts ``model: "auto"`` requests and resolves them to a cost-
appropriate concrete model before cache lookup.

Exports
-------
ComplexityLevel
    Enum of classification outcomes (``LOW`` / ``HIGH``).
ComplexityClassifier
    Heuristic classifier — token count + keyword signals.
RoutingResult
    Returned by :class:`ModelRouter.resolve`; carries the resolved
    model name (or ``None`` when routing was not applied).
ModelRouter
    Resolves trigger-model requests to concrete models; mutates
    ``ChatCompletionRequest.model`` in place.
RoutingDisabledError
    Raised when routing is disabled and the trigger model is used.
"""

from src.routing.classifier import ComplexityClassifier, ComplexityLevel
from src.routing.router import ModelRouter, RoutingDisabledError, RoutingResult

__all__ = [
    "ComplexityClassifier",
    "ComplexityLevel",
    "ModelRouter",
    "RoutingDisabledError",
    "RoutingResult",
]
