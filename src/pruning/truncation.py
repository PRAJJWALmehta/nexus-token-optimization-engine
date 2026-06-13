"""Token-budget-aware conversation truncator for prompt pruning.

Trims older messages from long conversations to bring the estimated token
count within a configurable budget.

Token estimation
----------------
Uses ``len(content) // 4`` (character count divided by 4) as the token
estimate — consistent with the :class:`~src.routing.classifier.ComplexityClassifier`.
Multimodal content is estimated by summing only the ``text``-type parts.

Anchored messages (never removed)
----------------------------------
* All system messages
* The first user message (establishes conversation context)
* The last user message (current turn)
* Any assistant or tool messages *after* the last user message
  (current turn tail)

Removal strategy
-----------------
Non-anchored messages are removed from the **oldest first** (from the
beginning of the non-anchored window toward the current turn).

Tool call / tool result pairs are treated as **atomic units**: removing an
assistant message that contains ``tool_calls`` also removes the immediately
following ``tool`` (function-result) messages that reference the same call
IDs, and vice versa.

Short-circuit
--------------
If the total estimated token count is already below the budget, the
transform returns a deep copy without modifying the message list.
If ``budget == 0``, truncation is disabled entirely.
"""

from __future__ import annotations

from typing import Any, Optional

from src.models.chat import ChatCompletionRequest, ChatMessage


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------


def _estimate_content_tokens(content: Any) -> int:
    """Return estimated token count for a message content field."""
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content) // 4
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                total += len(part.get("text", "")) // 4
        return total
    return 0


def _estimate_message_tokens(msg: ChatMessage) -> int:
    return _estimate_content_tokens(msg.content)


def _estimate_total_tokens(messages: list[ChatMessage]) -> int:
    return sum(_estimate_message_tokens(m) for m in messages)


# ---------------------------------------------------------------------------
# Anchor detection
# ---------------------------------------------------------------------------


def _find_anchors(messages: list[ChatMessage]) -> set[int]:
    """Return the set of indices in *messages* that are anchored (must keep).

    Anchored:
    - All system messages
    - First user message
    - Last user message  (if differs from first)
    - All messages after the last user message (current turn tail)
    """
    anchors: set[int] = set()

    # System messages
    for i, msg in enumerate(messages):
        if msg.role == "system":
            anchors.add(i)

    # First user message
    first_user_idx: Optional[int] = None
    for i, msg in enumerate(messages):
        if msg.role == "user":
            first_user_idx = i
            break

    if first_user_idx is not None:
        anchors.add(first_user_idx)

    # Last user message + current turn tail
    last_user_idx: Optional[int] = None
    for i, msg in enumerate(messages):
        if msg.role == "user":
            last_user_idx = i

    if last_user_idx is not None:
        # Anchor last user + everything after it (current turn tail)
        for i in range(last_user_idx, len(messages)):
            anchors.add(i)

    return anchors


# ---------------------------------------------------------------------------
# Tool pair detection
# ---------------------------------------------------------------------------


def _get_tool_call_ids(msg: ChatMessage) -> set[str]:
    """Return the set of tool call IDs emitted by an assistant message."""
    ids: set[str] = set()
    if msg.role == "assistant" and msg.tool_calls:
        for tc in msg.tool_calls:
            if isinstance(tc, dict):
                tc_id = tc.get("id")
                if tc_id:
                    ids.add(tc_id)
    return ids


def _find_tool_pair_indices(messages: list[ChatMessage], idx: int) -> set[int]:
    """Return all message indices that form a tool-call pair with *idx*.

    If *idx* is an assistant message with tool_calls, returns the indices
    of the immediately following tool messages that respond to those calls.

    If *idx* is a tool message, returns the index of the assistant message
    that initiated the call.
    """
    paired: set[int] = set()
    msg = messages[idx]

    if msg.role == "assistant" and msg.tool_calls:
        call_ids = _get_tool_call_ids(msg)
        # Look forward for tool responses
        for j in range(idx + 1, len(messages)):
            if messages[j].role == "tool" and messages[j].tool_call_id in call_ids:
                paired.add(j)
            elif messages[j].role not in ("tool",):
                break

    elif msg.role == "tool" and msg.tool_call_id:
        # Look backward for the assistant that made the call
        target_id = msg.tool_call_id
        for j in range(idx - 1, -1, -1):
            if messages[j].role == "assistant":
                call_ids = _get_tool_call_ids(messages[j])
                if target_id in call_ids:
                    paired.add(j)
                break

    return paired


# ---------------------------------------------------------------------------
# Truncation logic
# ---------------------------------------------------------------------------


class ConversationTruncator:
    """Pruning transform that enforces a token budget on message history.

    Parameters
    ----------
    budget:
        Maximum estimated token count. ``0`` disables truncation.
    """

    def __init__(self, budget: int = 16000) -> None:
        self._budget = budget

    def transform(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Return a deep copy of *request* trimmed to the token budget.

        Parameters
        ----------
        request:
            The incoming chat completion request to truncate.

        Returns
        -------
        ChatCompletionRequest
            A new request with older messages removed if the budget was
            exceeded.  Anchored messages are always preserved.
        """
        pruned = request.model_copy(deep=True)

        # Budget = 0 → disabled
        if self._budget == 0:
            return pruned

        messages = list(pruned.messages)

        # Short-circuit: already within budget
        if _estimate_total_tokens(messages) <= self._budget:
            return pruned

        anchors = _find_anchors(messages)

        # Build list of removable indices (non-anchored), oldest first
        removable = [i for i in range(len(messages)) if i not in anchors]

        # Remove oldest first until within budget or nothing left to remove
        removed: set[int] = set()
        for idx in removable:
            if _estimate_total_tokens(
                [m for i, m in enumerate(messages) if i not in removed]
            ) <= self._budget:
                break

            if idx in removed:
                continue

            # Collect this index + any tool-pair partners
            to_remove = {idx} | _find_tool_pair_indices(messages, idx)
            # Only remove non-anchored indices from the pair
            to_remove = {i for i in to_remove if i not in anchors}
            removed |= to_remove

        pruned.messages = [m for i, m in enumerate(messages) if i not in removed]
        return pruned
