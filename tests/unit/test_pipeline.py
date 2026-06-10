"""Unit tests for src.pruning.pipeline.PruningPipeline."""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.pruning.pipeline import PruningPipeline, PruningResult


def _make_request(*messages: ChatMessage) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="gpt-4", messages=list(messages))


def _system(content: str) -> ChatMessage:
    return ChatMessage(role="system", content=content)


def _user(content: str) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _assistant(content: str) -> ChatMessage:
    return ChatMessage(role="assistant", content=content)


def _pad(n: int) -> str:
    return "x" * n


# ---------------------------------------------------------------------------
# Full pipeline execution
# ---------------------------------------------------------------------------


class TestFullPipeline:
    def test_returns_pruning_result(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert isinstance(result, PruningResult)

    def test_tokens_before_after_present(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert result.tokens_before >= 0
        assert result.tokens_after >= 0

    def test_tokens_saved_non_negative(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert result.tokens_saved >= 0

    def test_all_four_transforms_applied(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello world"))
        result = p.run(req)
        assert "whitespace" in result.transforms_applied
        assert "comments" in result.transforms_applied
        assert "dedup" in result.transforms_applied
        assert "truncation" in result.transforms_applied

    def test_transform_order_whitespace_first(self):
        """Verify whitespace comes before comments in the applied list."""
        p = PruningPipeline()
        req = _make_request(_user("Hello world"))
        result = p.run(req)
        idx_ws = result.transforms_applied.index("whitespace")
        idx_co = result.transforms_applied.index("comments")
        assert idx_ws < idx_co

    def test_whitespace_is_actually_normalised(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert result.request.messages[0].content == "Hello world"

    def test_duplicate_system_removed(self):
        p = PruningPipeline()
        req = _make_request(
            _system("You are helpful."),
            _user("Hi"),
            _system("You are helpful."),
        )
        result = p.run(req)
        system_msgs = [m for m in result.request.messages if m.role == "system"]
        assert len(system_msgs) == 1


# ---------------------------------------------------------------------------
# Individual toggles
# ---------------------------------------------------------------------------


class TestIndividualToggles:
    def test_whitespace_disabled(self):
        p = PruningPipeline(normalize_whitespace=False)
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert "whitespace" not in result.transforms_applied
        # Content unchanged
        assert "Hello    world" in result.request.messages[0].content

    def test_comments_disabled(self):
        p = PruningPipeline(strip_comments=False)
        code = "```python\nx = 1  # comment\n```"
        req = _make_request(_user(code))
        result = p.run(req)
        assert "comments" not in result.transforms_applied
        assert "# comment" in result.request.messages[0].content

    def test_dedup_disabled(self):
        p = PruningPipeline(deduplicate_system=False)
        req = _make_request(_system("Dup"), _user("hi"), _system("Dup"))
        result = p.run(req)
        assert "dedup" not in result.transforms_applied
        assert len([m for m in result.request.messages if m.role == "system"]) == 2

    def test_truncation_disabled(self):
        p = PruningPipeline(truncate_conversation=False, token_budget=1)
        req = _make_request(_user(_pad(4000)))  # well over budget
        result = p.run(req)
        assert "truncation" not in result.transforms_applied
        # Message count unchanged (not truncated)
        assert len(result.request.messages) == 1


# ---------------------------------------------------------------------------
# All disabled → original returned
# ---------------------------------------------------------------------------


class TestAllDisabled:
    def test_all_disabled_returns_original_content(self):
        p = PruningPipeline(
            normalize_whitespace=False,
            strip_comments=False,
            deduplicate_system=False,
            truncate_conversation=False,
        )
        req = _make_request(_user("Hello    world"))
        result = p.run(req)
        assert result.request.messages[0].content == "Hello    world"
        assert result.transforms_applied == []

    def test_all_disabled_zero_saved(self):
        p = PruningPipeline(
            normalize_whitespace=False,
            strip_comments=False,
            deduplicate_system=False,
            truncate_conversation=False,
        )
        req = _make_request(_user("Test"))
        result = p.run(req)
        assert result.tokens_saved == 0


# ---------------------------------------------------------------------------
# Error resilience: one transform failing doesn't block others
# ---------------------------------------------------------------------------


class TestErrorResilience:
    def test_one_transform_error_continues_pipeline(self, monkeypatch):
        """If WhitespaceNormalizer raises, CommentStripper should still run."""
        from src.pruning import normalizer as norm_mod

        original_transform = norm_mod.WhitespaceNormalizer.transform

        call_count = {"comments": 0}

        def bad_transform(self, req):
            raise RuntimeError("Simulated normalizer failure")

        from src.pruning import comments as comm_mod

        original_comment_transform = comm_mod.CommentStripper.transform

        def counting_transform(self, req):
            call_count["comments"] += 1
            return original_comment_transform(self, req)

        monkeypatch.setattr(norm_mod.WhitespaceNormalizer, "transform", bad_transform)
        monkeypatch.setattr(comm_mod.CommentStripper, "transform", counting_transform)

        p = PruningPipeline()
        req = _make_request(_user("Hello world"))
        result = p.run(req)

        # Whitespace failed — not in applied
        assert "whitespace" not in result.transforms_applied
        # But comments should still have been attempted
        assert call_count["comments"] == 1


# ---------------------------------------------------------------------------
# Token counting accuracy
# ---------------------------------------------------------------------------


class TestTokenCounting:
    def test_tokens_before_matches_estimate(self):
        content = _pad(400)  # 100 tokens
        p = PruningPipeline(
            normalize_whitespace=False,
            strip_comments=False,
            deduplicate_system=False,
            truncate_conversation=False,
        )
        req = _make_request(_user(content))
        result = p.run(req)
        assert result.tokens_before == 100

    def test_whitespace_reduction_reflected_in_tokens_after(self):
        # 100 spaces → 1 space after normalization
        content = " " * 400  # 400 chars = 100 tokens
        p = PruningPipeline(
            normalize_whitespace=True,
            strip_comments=False,
            deduplicate_system=False,
            truncate_conversation=False,
        )
        req = _make_request(_user(content))
        result = p.run(req)
        assert result.tokens_after < result.tokens_before
        assert result.tokens_saved > 0


# ---------------------------------------------------------------------------
# Immutability of input
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_original_request_not_mutated(self):
        p = PruningPipeline()
        req = _make_request(_user("Hello    world"), _system("Dup"), _system("Dup"))
        original_msg_count = len(req.messages)
        original_content = req.messages[0].content
        p.run(req)
        assert req.messages[0].content == original_content
        assert len(req.messages) == original_msg_count
