"""Unit tests for src.pruning.dedup.SystemDeduplicator."""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.pruning.dedup import SystemDeduplicator


def _make_request(*messages: ChatMessage) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="gpt-4", messages=list(messages))


def _system(content: str, name: str = None) -> ChatMessage:
    return ChatMessage(role="system", content=content, name=name)


def _user(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _assistant(content: str) -> ChatMessage:
    return ChatMessage(role="assistant", content=content)


@pytest.fixture
def deduplicator() -> SystemDeduplicator:
    return SystemDeduplicator()


# ---------------------------------------------------------------------------
# Exact duplicate removal
# ---------------------------------------------------------------------------


class TestExactDuplicateRemoval:
    def test_exact_duplicate_removed(self, deduplicator):
        req = _make_request(
            _system("You are helpful."),
            _user("Hello"),
            _system("You are helpful."),
        )
        out = deduplicator.transform(req)
        system_msgs = [m for m in out.messages if m.role == "system"]
        assert len(system_msgs) == 1

    def test_first_occurrence_kept(self, deduplicator):
        req = _make_request(
            _system("First"),
            _system("First"),
        )
        out = deduplicator.transform(req)
        assert len(out.messages) == 1
        assert out.messages[0].content == "First"

    def test_multiple_duplicates_collapsed_to_one(self, deduplicator):
        req = _make_request(
            _system("Repeat"),
            _system("Repeat"),
            _system("Repeat"),
            _system("Repeat"),
        )
        out = deduplicator.transform(req)
        assert len(out.messages) == 1


# ---------------------------------------------------------------------------
# Whitespace-only difference treated as duplicate
# ---------------------------------------------------------------------------


class TestWhitespaceDifference:
    def test_trailing_space_treated_as_duplicate(self, deduplicator):
        req = _make_request(
            _system("You are helpful."),
            _system("You are helpful.   "),  # trailing spaces
        )
        out = deduplicator.transform(req)
        assert len([m for m in out.messages if m.role == "system"]) == 1

    def test_extra_blank_line_treated_as_duplicate(self, deduplicator):
        req = _make_request(
            _system("Line one.\nLine two."),
            _system("Line one.\n\nLine two."),  # extra blank line
        )
        out = deduplicator.transform(req)
        system_msgs = [m for m in out.messages if m.role == "system"]
        assert len(system_msgs) == 1


# ---------------------------------------------------------------------------
# Different content preserved
# ---------------------------------------------------------------------------


class TestDifferentContent:
    def test_different_content_preserved(self, deduplicator):
        req = _make_request(
            _system("You are helpful."),
            _system("You are concise."),
        )
        out = deduplicator.transform(req)
        assert len([m for m in out.messages if m.role == "system"]) == 2

    def test_three_different_systems_all_kept(self, deduplicator):
        req = _make_request(
            _system("A"),
            _system("B"),
            _system("C"),
        )
        out = deduplicator.transform(req)
        assert len(out.messages) == 3


# ---------------------------------------------------------------------------
# Name field identity
# ---------------------------------------------------------------------------


class TestNameFieldIdentity:
    def test_different_names_treated_as_distinct(self, deduplicator):
        req = _make_request(
            _system("Same content.", name="rules"),
            _system("Same content.", name="constraints"),
        )
        out = deduplicator.transform(req)
        assert len([m for m in out.messages if m.role == "system"]) == 2

    def test_same_name_and_content_deduplicated(self, deduplicator):
        req = _make_request(
            _system("Same content.", name="rules"),
            _system("Same content.", name="rules"),
        )
        out = deduplicator.transform(req)
        assert len([m for m in out.messages if m.role == "system"]) == 1

    def test_named_and_unnamed_treated_as_distinct(self, deduplicator):
        req = _make_request(
            _system("Same content."),          # no name
            _system("Same content.", name="x"),  # has name
        )
        out = deduplicator.transform(req)
        assert len([m for m in out.messages if m.role == "system"]) == 2


# ---------------------------------------------------------------------------
# Message ordering preservation
# ---------------------------------------------------------------------------


class TestOrderingPreservation:
    def test_ordering_preserved_after_dedup(self, deduplicator):
        req = _make_request(
            _system("A"),
            _user("User 1"),
            _system("A"),           # duplicate — should be removed
            _assistant("Reply 1"),
            _user("User 2"),
        )
        out = deduplicator.transform(req)
        roles = [m.role for m in out.messages]
        assert roles == ["system", "user", "assistant", "user"]

    def test_non_system_messages_positions_unchanged(self, deduplicator):
        req = _make_request(
            _system("Sys"),
            _user("U1"),
            _system("Sys"),  # dup
            _user("U2"),
        )
        out = deduplicator.transform(req)
        assert out.messages[0].role == "system"
        assert out.messages[1].content == "U1"
        assert out.messages[2].content == "U2"


# ---------------------------------------------------------------------------
# Non-system messages untouched
# ---------------------------------------------------------------------------


class TestNonSystemMessages:
    def test_duplicate_user_messages_preserved(self, deduplicator):
        req = _make_request(
            _system("Sys"),
            _user("Same question"),
            _user("Same question"),
        )
        out = deduplicator.transform(req)
        user_msgs = [m for m in out.messages if m.role == "user"]
        assert len(user_msgs) == 2

    def test_duplicate_assistant_messages_preserved(self, deduplicator):
        req = _make_request(
            _system("Sys"),
            _assistant("Same answer"),
            _assistant("Same answer"),
        )
        out = deduplicator.transform(req)
        asst_msgs = [m for m in out.messages if m.role == "assistant"]
        assert len(asst_msgs) == 2


# ---------------------------------------------------------------------------
# Short-circuit: single system message
# ---------------------------------------------------------------------------


class TestShortCircuit:
    def test_single_system_message_unchanged(self, deduplicator):
        req = _make_request(_system("Only one."), _user("Hi"))
        out = deduplicator.transform(req)
        assert len(out.messages) == 2

    def test_no_system_message_unchanged(self, deduplicator):
        req = _make_request(_user("No system here"))
        out = deduplicator.transform(req)
        assert len(out.messages) == 1


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_original_not_mutated(self, deduplicator):
        req = _make_request(
            _system("Dup"),
            _user("hi"),
            _system("Dup"),
        )
        original_len = len(req.messages)
        deduplicator.transform(req)
        assert len(req.messages) == original_len
