"""Unit tests for src.pruning.comments.CommentStripper."""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.pruning.comments import CommentStripper


def _make_request(*messages: ChatMessage) -> ChatCompletionRequest:
    return ChatCompletionRequest(model="gpt-4", messages=list(messages))


def _user(content) -> ChatMessage:
    return ChatMessage(role="user", content=content)


def _system(content: str) -> ChatMessage:
    return ChatMessage(role="system", content=content)


def _fenced(lang: str, code: str) -> str:
    """Wrap *code* in a fenced block with optional *lang* info string."""
    fence = f"```{lang}\n" if lang else "```\n"
    return fence + code + "\n```"


@pytest.fixture
def stripper() -> CommentStripper:
    return CommentStripper()


# ---------------------------------------------------------------------------
# Python comments
# ---------------------------------------------------------------------------


class TestPythonComments:
    def test_single_line_comment_removed(self, stripper):
        code = _fenced("python", "x = 1  # set x\nreturn x")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "# set x" not in out.messages[0].content
        assert "x = 1" in out.messages[0].content

    def test_comment_only_line_removed(self, stripper):
        code = _fenced("python", "# This sets x\nx = 1")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "# This sets x" not in out.messages[0].content
        assert "x = 1" in out.messages[0].content

    def test_multiple_comments_removed(self, stripper):
        code = _fenced("py", "# import os\nimport sys  # stdlib\nprint('hello')")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        result = out.messages[0].content
        assert "# import os" not in result
        assert "# stdlib" not in result
        assert "import sys" in result
        assert "print('hello')" in result


# ---------------------------------------------------------------------------
# JavaScript / C-style comments
# ---------------------------------------------------------------------------


class TestJavaScriptComments:
    def test_single_line_comment_removed(self, stripper):
        code = _fenced("javascript", "const x = 1; // set x\nconsole.log(x);")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "// set x" not in out.messages[0].content
        assert "const x = 1;" in out.messages[0].content

    def test_js_alias_detected(self, stripper):
        code = _fenced("js", "const y = 2; // y value")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "// y value" not in out.messages[0].content

    def test_typescript_detected(self, stripper):
        code = _fenced("typescript", "const z: number = 3; // z")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "// z" not in out.messages[0].content


class TestCStyleMultilineComments:
    def test_multiline_comment_removed(self, stripper):
        code = _fenced("java", "/* This is\na comment */\nint x = 1;")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        result = out.messages[0].content
        assert "/* This is" not in result
        assert "a comment */" not in result
        assert "int x = 1;" in result

    def test_inline_block_comment_removed(self, stripper):
        code = _fenced("c", "int x = /* value */ 1;")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "/* value */" not in out.messages[0].content


# ---------------------------------------------------------------------------
# HTML comments
# ---------------------------------------------------------------------------


class TestHtmlComments:
    def test_html_comment_removed(self, stripper):
        code = _fenced("html", "<div><!-- remove me --></div>")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "<!-- remove me -->" not in out.messages[0].content
        assert "<div>" in out.messages[0].content

    def test_multiline_html_comment_removed(self, stripper):
        code = _fenced("html", "<!--\nthis is\na comment\n-->\n<p>text</p>")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        result = out.messages[0].content
        assert "<!--" not in result
        assert "<p>text</p>" in result


# ---------------------------------------------------------------------------
# SQL comments
# ---------------------------------------------------------------------------


class TestSqlComments:
    def test_sql_single_line_comment_removed(self, stripper):
        code = _fenced("sql", "SELECT * FROM users -- get all users")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "-- get all users" not in out.messages[0].content
        assert "SELECT * FROM users" in out.messages[0].content


# ---------------------------------------------------------------------------
# No fence info string (default C-style)
# ---------------------------------------------------------------------------


class TestDefaultFallback:
    def test_no_lang_uses_c_style(self, stripper):
        code = _fenced("", "const a = 1; // comment\nconst b = 2;")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "// comment" not in out.messages[0].content
        assert "const b = 2;" in out.messages[0].content


# ---------------------------------------------------------------------------
# String literal preservation
# ---------------------------------------------------------------------------


class TestStringLiteralPreservation:
    def test_hash_in_string_preserved(self, stripper):
        code = _fenced("python", 'url = "https://example.com/#section"')
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "#section" in out.messages[0].content

    def test_double_slash_in_string_preserved(self, stripper):
        code = _fenced("javascript", 'const url = "https://example.com";')
        req = _make_request(_user(code))
        out = stripper.transform(req)
        assert "https://example.com" in out.messages[0].content

    def test_comment_outside_string_removed_not_inside(self, stripper):
        code = _fenced("python", 'msg = "# not a comment"  # real comment')
        req = _make_request(_user(code))
        out = stripper.transform(req)
        result = out.messages[0].content
        assert "# not a comment" in result  # string preserved
        assert "# real comment" not in result  # comment removed


# ---------------------------------------------------------------------------
# Prose preservation
# ---------------------------------------------------------------------------


class TestProsePreservation:
    def test_markdown_heading_not_touched(self, stripper):
        content = "# My Heading\n\nSome text."
        req = _make_request(_user(content))
        out = stripper.transform(req)
        assert "# My Heading" in out.messages[0].content

    def test_url_in_prose_not_touched(self, stripper):
        content = "Visit https://example.com for more info."
        req = _make_request(_user(content))
        out = stripper.transform(req)
        assert "https://example.com" in out.messages[0].content

    def test_no_code_block_request_unchanged(self, stripper):
        content = "Please help me. # not code"
        req = _make_request(_user(content))
        out = stripper.transform(req)
        assert out.messages[0].content == content


# ---------------------------------------------------------------------------
# Blank line cleanup
# ---------------------------------------------------------------------------


class TestBlankLineCleanup:
    def test_comment_only_lines_removed_not_blanked(self, stripper):
        code = _fenced("python", "# comment 1\n# comment 2\nx = 1")
        req = _make_request(_user(code))
        out = stripper.transform(req)
        result = out.messages[0].content
        # Should not have multiple consecutive blank lines
        assert "\n\n\n" not in result
        assert "x = 1" in result


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_original_not_mutated(self, stripper):
        code = _fenced("python", "x = 1  # comment")
        req = _make_request(_user(code))
        original_content = req.messages[0].content
        stripper.transform(req)
        assert req.messages[0].content == original_content


# ---------------------------------------------------------------------------
# Short-circuit
# ---------------------------------------------------------------------------


class TestShortCircuit:
    def test_no_fence_request_returned_unchanged(self, stripper):
        req = _make_request(_user("Plain text without any code blocks."))
        out = stripper.transform(req)
        assert out.messages[0].content == "Plain text without any code blocks."
