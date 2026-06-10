"""Unit tests for src.pruning.normalizer.WhitespaceNormalizer."""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.pruning.normalizer import WhitespaceNormalizer


def _make_request(*messages: ChatMessage) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="gpt-4", messages=list(messages))


def _user(content: str, **kwargs) -> ChatMessage:
    return ChatMessage(role="user", content=content, **kwargs)


def _system(content: str) -> ChatMessage:
    return ChatMessage(role="system", content=content)


def _assistant(content: str) -> ChatMessage:
    return ChatMessage(role="assistant", content=content)


@pytest.fixture
def normalizer() -> WhitespaceNormalizer:
    return WhitespaceNormalizer()


# ---------------------------------------------------------------------------
# Prose normalisation
# ---------------------------------------------------------------------------


class TestProseNormalisation:
    def test_consecutive_spaces_collapsed(self, normalizer):
        req = _make_request(_user("Hello    world"))
        out = normalizer.transform(req)
        assert out.messages[0].content == "Hello world"

    def test_consecutive_tabs_collapsed(self, normalizer):
        req = _make_request(_user("Hello\t\t\tworld"))
        out = normalizer.transform(req)
        assert out.messages[0].content == "Hello world"

    def test_mixed_whitespace_collapsed(self, normalizer):
        req = _make_request(_user("Hello \t  world"))
        out = normalizer.transform(req)
        assert out.messages[0].content == "Hello world"

    def test_crlf_normalised_to_lf(self, normalizer):
        req = _make_request(_user("line1\r\nline2\r\nline3"))
        out = normalizer.transform(req)
        assert "\r" not in out.messages[0].content
        assert out.messages[0].content == "line1\nline2\nline3"

    def test_cr_normalised_to_lf(self, normalizer):
        req = _make_request(_user("line1\rline2"))
        out = normalizer.transform(req)
        assert out.messages[0].content == "line1\nline2"

    def test_trailing_whitespace_stripped(self, normalizer):
        req = _make_request(_user("hello   \nworld  "))
        out = normalizer.transform(req)
        lines = out.messages[0].content.split("\n")
        for line in lines:
            assert not line.endswith(" "), f"Trailing space in: {repr(line)}"

    def test_leading_whitespace_preserved(self, normalizer):
        req = _make_request(_user("    indented line"))
        out = normalizer.transform(req)
        assert out.messages[0].content.startswith("    ")

    def test_three_blank_lines_collapsed_to_two(self, normalizer):
        req = _make_request(_user("a\n\n\n\n\nb"))
        out = normalizer.transform(req)
        assert out.messages[0].content == "a\n\n\nb"

    def test_two_blank_lines_preserved(self, normalizer):
        req = _make_request(_user("a\n\n\nb"))
        out = normalizer.transform(req)
        # Two consecutive blank lines (3 \n together) — allowed
        assert out.messages[0].content == "a\n\n\nb"


# ---------------------------------------------------------------------------
# Code block preservation
# ---------------------------------------------------------------------------


class TestCodeBlockPreservation:
    def test_code_block_whitespace_preserved(self, normalizer):
        code = "```python\ndef foo():\n    x  =  1   # multiple spaces\n    return x\n```"
        req = _make_request(_user(code))
        out = normalizer.transform(req)
        # The internal spaces inside the code block must be unchanged
        assert "    x  =  1   # multiple spaces" in out.messages[0].content

    def test_prose_around_code_block_normalised(self, normalizer):
        content = "Some    text before\n```\ncode   block\n```\nSome    text after"
        req = _make_request(_user(content))
        out = normalizer.transform(req)
        result = out.messages[0].content
        assert "Some text before" in result
        assert "Some text after" in result
        assert "code   block" in result  # code block preserved

    def test_tilde_fence_preserved(self, normalizer):
        code = "~~~js\nconst x  =  1;\n~~~"
        req = _make_request(_user(code))
        out = normalizer.transform(req)
        assert "const x  =  1;" in out.messages[0].content

    def test_unclosed_fence_treated_as_prose(self, normalizer):
        content = "```\nunclosed   code"
        req = _make_request(_user(content))
        out = normalizer.transform(req)
        # Should not crash; content normalised as prose
        assert out.messages[0].content is not None


# ---------------------------------------------------------------------------
# Multimodal content
# ---------------------------------------------------------------------------


class TestMultimodalContent:
    def test_text_parts_normalised(self, normalizer):
        content = [{"type": "text", "text": "Hello    world"}]
        req = _make_request(_user(content))  # type: ignore[arg-type]
        out = normalizer.transform(req)
        assert out.messages[0].content[0]["text"] == "Hello world"

    def test_image_parts_preserved_unchanged(self, normalizer):
        image_part = {"type": "image_url", "image_url": {"url": "https://example.com/img.png"}}
        content = [{"type": "text", "text": "Look at this:   "}, image_part]
        req = _make_request(_user(content))  # type: ignore[arg-type]
        out = normalizer.transform(req)
        result_content = out.messages[0].content
        assert result_content[1] == image_part

    def test_none_content_unchanged(self, normalizer):
        msg = ChatMessage(role="user", content=None)
        req = _make_request(msg)
        out = normalizer.transform(req)
        assert out.messages[0].content is None


# ---------------------------------------------------------------------------
# All message roles affected
# ---------------------------------------------------------------------------


class TestMessageRoleScope:
    def test_system_message_normalised(self, normalizer):
        req = _make_request(_system("You are   a helpful assistant."))
        out = normalizer.transform(req)
        assert out.messages[0].content == "You are a helpful assistant."

    def test_assistant_message_normalised(self, normalizer):
        req = _make_request(_assistant("Here is   the answer."))
        out = normalizer.transform(req)
        assert out.messages[0].content == "Here is the answer."

    def test_all_roles_normalised(self, normalizer):
        req = _make_request(
            _system("You are   helpful."),
            _user("What is   2+2?"),
            _assistant("It is   4."),
        )
        out = normalizer.transform(req)
        assert out.messages[0].content == "You are helpful."
        assert out.messages[1].content == "What is 2+2?"
        assert out.messages[2].content == "It is 4."


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_original_request_not_mutated(self, normalizer):
        req = _make_request(_user("Hello    world"))
        original_content = req.messages[0].content
        normalizer.transform(req)
        assert req.messages[0].content == original_content
