"""System instruction deduplicator for prompt pruning.

Detects and removes duplicate system messages from a
:class:`~src.models.chat.ChatCompletionRequest`.

Deduplication rules
--------------------
* Only ``role: "system"`` messages are candidates for deduplication.
* Two system messages are considered **identical** when their ``content``
  is equal after whitespace normalisation (collapse runs, strip trailing
  whitespace, normalise line endings).
* Messages with different ``name`` fields are treated as **distinct**,
  even if their content is identical.  ``None`` and ``""`` are treated as
  the same (both mean "no name").
* When duplicates are found, only the **first** occurrence is kept; later
  occurrences are removed.
* Non-system messages are never deduplicated.
* The relative ordering of all remaining messages is preserved.

Short-circuit
-------------
If the request contains ≤ 1 system message, the transform returns a deep
copy immediately without scanning message content.
"""

from __future__ import annotations

import re

from src.models.chat import ChatCompletionRequest, ChatMessage


def _normalise_for_comparison(text: str) -> str:
    """Return a whitespace-normalised version of *text* for equality checks."""
    return " ".join(text.split())


def _content_key(content) -> str:
    """Produce a comparable string key from a message content value."""
    if content is None:
        return ""
    if isinstance(content, str):
        return _normalise_for_comparison(content)
    if isinstance(content, list):
        # Concatenate text parts only
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return _normalise_for_comparison(" ".join(parts))
    return str(content)


def _name_key(msg: ChatMessage) -> str:
    """Canonical name value: treat None and '' as equivalent."""
    return (msg.name or "").strip()


class SystemDeduplicator:
    """Pruning transform that collapses duplicate system messages.

    Applies a short-circuit when ≤ 1 system message is present.
    Does not modify non-system messages.
    """

    def transform(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Return a deep copy of *request* with duplicate system messages removed.

        Parameters
        ----------
        request:
            The incoming chat completion request to deduplicate.

        Returns
        -------
        ChatCompletionRequest
            A new request object with at most one instance of each
            unique (content, name) system message combination.
        """
        pruned = request.model_copy(deep=True)

        # Short-circuit: count system messages
        system_count = sum(1 for m in pruned.messages if m.role == "system")
        if system_count <= 1:
            return pruned

        seen: set[tuple[str, str]] = set()
        new_messages: list[ChatMessage] = []

        for msg in pruned.messages:
            if msg.role != "system":
                new_messages.append(msg)
                continue

            fingerprint = (_content_key(msg.content), _name_key(msg))
            if fingerprint in seen:
                # Duplicate — drop it
                continue
            seen.add(fingerprint)
            new_messages.append(msg)

        pruned.messages = new_messages
        return pruned
