"""Unit tests for src.pruning.truncation.ConversationTruncator."""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.pruning.truncation import ConversationTruncator, _estimate_total_tokens


def _make_request(*messages: ChatMessage) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="gpt-4", messages=list(messages))


def _system(content: str) -> ChatMessage:
    return ChatMessage(role="system", content=content)


def _user(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _assistant(content: str, tool_calls=None) -> ChatMessage:
    return ChatMessage(role="assistant", content=content, tool_calls=tool_calls)


def _tool(content: str, call_id: str) -> ChatMessage:
    return ChatMessage(role="tool", content=content, tool_call_id=call_id)


def _pad(n_chars: int) -> str:
    """Return a string of length *n_chars* (to easily control token estimates)."""
    return "x" * n_chars


# ---------------------------------------------------------------------------
# Under-budget: unchanged
# ---------------------------------------------------------------------------


class TestUnderBudget:
    def test_small_request_unchanged(self):
        t = ConversationTruncator(budget=16000)
        req = _make_request(_system("Short"), _user("Question"), _assistant("Answer"))
        out = t.transform(req)
        assert len(out.messages) == 3

    def test_total_estimate_under_budget_unchanged(self):
        t = ConversationTruncator(budget=1000)
        # 10 chars = ~2 tokens per message; 3 messages = ~6 tokens
        req = _make_request(_system("Short sys"), _user("Short user"), _assistant("Short"))
        out = t.transform(req)
        assert len(out.messages) == 3


# ---------------------------------------------------------------------------
# Over-budget: truncation
# ---------------------------------------------------------------------------


class TestOverBudget:
    def test_over_budget_removes_messages(self):
        # Each message is 400 chars = 100 tokens; 4 messages = 400 tokens
        # Budget = 200 → need to remove ~200 tokens worth
        t = ConversationTruncator(budget=200)
        req = _make_request(
            _system(_pad(400)),    # anchored
            _user(_pad(400)),      # anchored (first + last user)
        )
        # Only 2 messages; only user is removable in theory but it's anchored
        # So nothing can be removed — anchors always preserved
        out = t.transform(req)
        assert len(out.messages) == 2  # both anchored

    def test_middle_messages_removed_over_budget(self):
        # Budget of 50 tokens; middle messages are 200 chars (~50 tokens) each
        # sys + user1 + asst1 + user2 → trim asst1
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),        # ~10 tok — anchored
            _user(_pad(40)),          # ~10 tok — anchored (first user)
            _assistant(_pad(200)),    # ~50 tok — removable
            _user(_pad(40)),          # ~10 tok — anchored (last user)
        )
        out = t.transform(req)
        roles = [m.role for m in out.messages]
        assert "assistant" not in roles
        assert roles == ["system", "user", "user"]


# ---------------------------------------------------------------------------
# Anchored message preservation
# ---------------------------------------------------------------------------


class TestAnchoredMessages:
    def test_system_messages_always_preserved(self):
        t = ConversationTruncator(budget=10)
        req = _make_request(
            _system(_pad(200)),   # ~50 tok — anchored
            _user(_pad(200)),     # ~50 tok — anchored (first+last user)
        )
        out = t.transform(req)
        assert any(m.role == "system" for m in out.messages)

    def test_first_user_message_preserved(self):
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),         # ~10 tok
            _user("first user"),       # anchored
            _assistant(_pad(200)),     # ~50 tok — removable
            _user("last user"),        # anchored (also last user)
        )
        out = t.transform(req)
        contents = [m.content for m in out.messages]
        assert "first user" in contents

    def test_last_user_message_preserved(self):
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),
            _user("first user"),
            _assistant(_pad(200)),
            _user("last user"),
        )
        out = t.transform(req)
        contents = [m.content for m in out.messages]
        assert "last user" in contents

    def test_current_turn_tail_preserved(self):
        # assistant message AFTER last user is anchored
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),
            _user("first"),
            _assistant(_pad(200)),   # removable (before last user)
            _user("last user"),
            _assistant("current reply"),  # anchored (after last user)
        )
        out = t.transform(req)
        contents = [m.content for m in out.messages]
        assert "current reply" in contents

    def test_only_anchored_messages_remain_when_all_trimmed(self):
        t = ConversationTruncator(budget=5)  # tiny budget
        req = _make_request(
            _system("Sys"),
            _user("First"),
            _assistant(_pad(400)),
            _assistant(_pad(400)),
            _user("Last"),
        )
        out = t.transform(req)
        roles = [m.role for m in out.messages]
        # All assistants (non-anchored) removed, system + first user + last user kept
        assert "system" in roles
        assert out.messages[-1].content == "Last"


# ---------------------------------------------------------------------------
# Middle-out removal order
# ---------------------------------------------------------------------------


class TestMiddleOutRemoval:
    def test_oldest_non_anchored_removed_first(self):
        t = ConversationTruncator(budget=80)
        req = _make_request(
            _system(_pad(40)),         # ~10 tok — anchored
            _user(_pad(40)),           # ~10 tok — anchored (first user)
            _assistant(_pad(200)),     # ~50 tok — removable (oldest)
            _assistant(_pad(200)),     # ~50 tok — removable
            _user(_pad(40)),           # ~10 tok — anchored (last user)
        )
        # Total ~130 tok, budget 80 → need to remove ~50 tok
        # Should remove first assistant only
        out = t.transform(req)
        asst_messages = [m for m in out.messages if m.role == "assistant"]
        assert len(asst_messages) == 1

    def test_message_ordering_preserved_after_truncation(self):
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),
            _user("first"),
            _assistant(_pad(200)),   # removed
            _user("last"),
        )
        out = t.transform(req)
        assert out.messages[0].role == "system"
        assert out.messages[1].content == "first"
        assert out.messages[2].content == "last"


# ---------------------------------------------------------------------------
# Tool call / result atomic pairing
# ---------------------------------------------------------------------------


class TestToolCallPairing:
    def test_tool_call_pair_removed_together(self):
        call = {"id": "call_1", "type": "function", "function": {"name": "do_thing"}}
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),
            _user("first user"),
            _assistant(_pad(100), tool_calls=[call]),  # ~25 tok + tool_calls
            _tool(_pad(100), call_id="call_1"),         # ~25 tok — pair
            _user("last user"),
        )
        out = t.transform(req)
        # Both assistant+tool should be removed or both kept
        roles = [m.role for m in out.messages]
        has_asst = "assistant" in roles
        has_tool = "tool" in roles
        assert has_asst == has_tool, "Tool call pair must be kept or removed together"


# ---------------------------------------------------------------------------
# Multimodal token estimation
# ---------------------------------------------------------------------------


class TestMultimodalTokenEstimation:
    def test_text_parts_counted(self):
        # 400 chars of text = 100 tokens
        content = [{"type": "text", "text": _pad(400)}]
        msg = ChatMessage(role="user", content=content)
        req = _make_request(msg)
        est = _estimate_total_tokens(req.messages)
        assert est == 100

    def test_image_parts_not_counted(self):
        content = [
            {"type": "text", "text": _pad(400)},
            {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}},
        ]
        msg = ChatMessage(role="user", content=content)
        req = _make_request(msg)
        est = _estimate_total_tokens(req.messages)
        assert est == 100  # only text counted


# ---------------------------------------------------------------------------
# Budget = 0 disables truncation
# ---------------------------------------------------------------------------


class TestBudgetZeroDisabled:
    def test_budget_zero_skips_truncation(self):
        # Even though it's way over budget, budget=0 means disabled
        t = ConversationTruncator(budget=0)
        req = _make_request(
            _system(_pad(2000)),
            _user(_pad(2000)),
            _assistant(_pad(2000)),
            _user(_pad(2000)),
        )
        out = t.transform(req)
        assert len(out.messages) == 4


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_original_not_mutated(self):
        t = ConversationTruncator(budget=60)
        req = _make_request(
            _system(_pad(40)),
            _user(_pad(40)),
            _assistant(_pad(400)),
            _user(_pad(40)),
        )
        original_len = len(req.messages)
        t.transform(req)
        assert len(req.messages) == original_len
