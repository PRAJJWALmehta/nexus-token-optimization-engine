"""Heuristic complexity classifier for dynamic model routing.

Classifies a :class:`~src.models.chat.ChatCompletionRequest` as either
**LOW** or **HIGH** complexity using two independent signals:

1. **Token count** — estimated from character length of relevant message
   content (``total_chars // 4``).  When the estimate meets or exceeds the
   configured threshold the request is classified HIGH.

2. **Keyword signals** — whole-word, case-insensitive scan of the last
   user message and all system messages.  A match on any configured keyword
   immediately classifies the request HIGH.

A request is HIGH if *either* signal triggers; otherwise it is LOW.

Message scope
-------------
Only the **last user message** and **all system messages** are analysed.
Assistant, tool, and function messages are excluded — they represent prior
model output, not the current task intent.

Multimodal content
------------------
When a message ``content`` field is a list (OpenAI vision format), the
classifier concatenates text parts (``{"type": "text", ...}``) and ignores
non-text parts such as ``image_url``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.models.chat import ChatCompletionRequest, ChatMessage

# Default keyword set (can be overridden via ROUTING_COMPLEXITY_KEYWORDS)
_DEFAULT_KEYWORDS: list[str] = [
    "refactor",
    "architect",
    "design",
    "optimize",
    "analyze",
    "debug",
    "review",
    "explain",
]


class ComplexityLevel(str, Enum):
    """Outcome of complexity classification."""

    LOW = "low"
    HIGH = "high"


@dataclass
class ComplexityResult:
    """Result returned by :class:`ComplexityClassifier.classify`."""

    level: ComplexityLevel
    tokens_est: int
    keyword_match: Optional[str] = None  # first keyword matched, or None


class ComplexityClassifier:
    """Heuristic complexity classifier.

    Parameters
    ----------
    token_threshold:
        Estimated token count at-or-above which a request is classified HIGH.
        Defaults to ``2000``.
    keywords:
        Iterable of strings to match (whole-word, case-insensitive).
        Defaults to :data:`_DEFAULT_KEYWORDS`.
    """

    def __init__(
        self,
        token_threshold: int = 2000,
        keywords: Optional[list[str]] = None,
    ) -> None:
        self._threshold = token_threshold
        raw_keywords = keywords if keywords is not None else _DEFAULT_KEYWORDS
        # Pre-compile one pattern per keyword for whole-word matching
        self._patterns: list[tuple[str, re.Pattern[str]]] = [
            (kw, re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE))
            for kw in raw_keywords
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, request: ChatCompletionRequest) -> ComplexityResult:
        """Classify *request* complexity.

        Parameters
        ----------
        request:
            The incoming chat completion request to classify.

        Returns
        -------
        ComplexityResult
            Contains the complexity level, estimated token count, and the
            first keyword matched (if any).
        """
        relevant = self._relevant_messages(request)
        text = self._extract_text(relevant)
        tokens_est = len(text) // 4

        # Signal 1: token count
        if tokens_est >= self._threshold:
            return ComplexityResult(
                level=ComplexityLevel.HIGH,
                tokens_est=tokens_est,
                keyword_match=None,
            )

        # Signal 2: keyword match
        kw = self._find_keyword(text)
        if kw is not None:
            return ComplexityResult(
                level=ComplexityLevel.HIGH,
                tokens_est=tokens_est,
                keyword_match=kw,
            )

        return ComplexityResult(level=ComplexityLevel.LOW, tokens_est=tokens_est)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _relevant_messages(request: ChatCompletionRequest) -> list[ChatMessage]:
        """Return system messages + the last user message.

        Assistant, tool, and function messages are excluded from analysis.
        If no user message exists, only system messages are returned (the
        classifier will default to LOW unless system content triggers HIGH).
        """
        system_msgs: list[ChatMessage] = [
            m for m in request.messages if m.role == "system"
        ]
        user_msgs: list[ChatMessage] = [
            m for m in request.messages if m.role == "user"
        ]
        # Take only the last user message
        last_user = [user_msgs[-1]] if user_msgs else []
        return system_msgs + last_user

    @staticmethod
    def _extract_text(messages: list[ChatMessage]) -> str:
        """Concatenate text content from *messages*.

        Handles both plain-string and list-of-parts (multimodal) content.
        Non-text parts (``image_url``, etc.) are silently skipped.
        """
        parts: list[str] = []
        for msg in messages:
            content = msg.content
            if not content:
                continue
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            parts.append(text)
        return " ".join(parts)

    def _find_keyword(self, text: str) -> Optional[str]:
        """Return the first matching keyword in *text*, or ``None``."""
        for keyword, pattern in self._patterns:
            if pattern.search(text):
                return keyword
        return None
