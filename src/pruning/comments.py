"""Code comment stripper for prompt pruning.

Removes code comments from fenced code blocks within message content.
Prose content outside code blocks is left completely untouched.

Supported comment syntax
------------------------
* Python / Shell / Ruby      : ``#`` single-line
* JS / TS / Java / C / Go / Rust : ``//`` single-line, ``/* ... */`` multi-line
* HTML / XML                 : ``<!-- ... -->``
* SQL / Lua                  : ``--`` single-line

String literal awareness
------------------------
A simple same-line heuristic is used: when a comment character appears
inside matched (single or double) quotes on the same line, the line is
left untouched.  This handles the common cases of URLs in strings and
string values that happen to contain comment-like syntax.

Design decisions
----------------
* Only fenced code blocks (````` ``` ````` or ``~~~``) are processed.
* The language is detected from the fence info string (e.g. ```` ```python ````).
* When no language is specified, C-style ``//`` and ``/* */`` patterns are used
  (minimal false-positive risk).
* Comment-only lines are removed entirely; trailing whitespace left by inline
  comment removal is stripped.
* Blank lines produced by comment removal are compacted (no double-blanks).
"""

from __future__ import annotations

import re
from typing import Any

from src.models.chat import ChatCompletionRequest, ChatMessage

# ---------------------------------------------------------------------------
# Language → comment pattern sets
# ---------------------------------------------------------------------------

# Each entry is (name, languages that use it, single-line prefix pattern, multiline pattern)
_PYTHON_LANGS = {"python", "py", "ruby", "rb", "shell", "sh", "bash", "zsh", "r"}
_C_STYLE_LANGS = {
    "javascript", "js", "typescript", "ts", "java", "c", "cpp", "c++",
    "csharp", "cs", "go", "rust", "rs", "kotlin", "kt", "swift", "scala",
    "php", "dart",
}
_HTML_LANGS = {"html", "xml", "svg", "xhtml"}
_SQL_LANGS = {"sql", "mysql", "postgresql", "postgres", "sqlite", "plsql"}


def _detect_comment_style(lang: str) -> str:
    """Return a style key for the given fence language label."""
    lang = lang.lower().strip()
    if lang in _PYTHON_LANGS:
        return "python"
    if lang in _C_STYLE_LANGS:
        return "c_style"
    if lang in _HTML_LANGS:
        return "html"
    if lang in _SQL_LANGS:
        return "sql"
    # Default: C-style (broadest, low false-positive risk without Python's #)
    return "c_style"


# ---------------------------------------------------------------------------
# Comment stripping helpers
# ---------------------------------------------------------------------------


def _is_inside_quotes(line: str, idx: int) -> bool:
    """Return True if *idx* in *line* falls inside a quoted string segment.

    Uses a simple state machine that tracks single/double quote open/close.
    Handles escaped quotes (``\\'`` / ``\\"``) naively — skips one char after
    a backslash.
    """
    in_single = False
    in_double = False
    i = 0
    while i < idx:
        ch = line[i]
        if ch == "\\":
            i += 2  # skip escaped char
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return in_single or in_double


def _strip_python_comments(lines: list[str]) -> list[str]:
    """Remove ``#`` single-line comments, skipping string-literal contexts."""
    result = []
    for line in lines:
        stripped = line.rstrip()
        idx = stripped.find("#")
        while idx != -1:
            if not _is_inside_quotes(stripped, idx):
                stripped = stripped[:idx].rstrip()
                break
            idx = stripped.find("#", idx + 1)
        result.append(stripped)
    return result


def _strip_c_style_comments(lines: list[str]) -> list[str]:
    """Remove ``//`` single-line and ``/* */`` multi-line C-style comments."""
    # First handle multi-line /* */ by joining into a single string
    text = "\n".join(lines)

    # Remove /* ... */ (non-greedy, including across lines)
    def remove_block_comments(t: str) -> str:
        result_parts = []
        i = 0
        while i < len(t):
            # Check for /* outside strings
            if t[i:i+2] == "/*" and not _is_inside_quotes(t[:i].split("\n")[-1], len(t[:i].split("\n")[-1])):
                end = t.find("*/", i + 2)
                if end == -1:
                    break  # unclosed — skip to end
                # Count newlines consumed so we don't collapse lines
                newlines = t[i:end+2].count("\n")
                result_parts.append("\n" * newlines)
                i = end + 2
            else:
                result_parts.append(t[i])
                i += 1
        return "".join(result_parts)

    text = remove_block_comments(text)

    # Now handle // single-line
    result = []
    for line in text.split("\n"):
        stripped = line.rstrip()
        idx = stripped.find("//")
        while idx != -1:
            if not _is_inside_quotes(stripped, idx):
                stripped = stripped[:idx].rstrip()
                break
            idx = stripped.find("//", idx + 2)
        result.append(stripped)
    return result


def _strip_html_comments(lines: list[str]) -> list[str]:
    """Remove ``<!-- ... -->`` comments (may span multiple lines)."""
    text = "\n".join(lines)
    # Remove <!-- ... --> non-greedily
    cleaned = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return cleaned.split("\n")


def _strip_sql_comments(lines: list[str]) -> list[str]:
    """Remove ``--`` single-line SQL comments."""
    result = []
    for line in lines:
        stripped = line.rstrip()
        idx = stripped.find("--")
        while idx != -1:
            if not _is_inside_quotes(stripped, idx):
                stripped = stripped[:idx].rstrip()
                break
            idx = stripped.find("--", idx + 2)
        result.append(stripped)
    return result


def _compact_blank_lines(lines: list[str]) -> list[str]:
    """Remove blank lines that are entirely empty after comment stripping,
    and collapse consecutive blank lines (more than 2) into 2."""
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                result.append("")
        else:
            blank_run = 0
            result.append(line)
    # Strip leading/trailing blank lines inside the block
    while result and result[0] == "":
        result.pop(0)
    while result and result[-1] == "":
        result.pop()
    return result


def _strip_comments_from_code(code_lines: list[str], style: str) -> list[str]:
    """Apply comment stripping to *code_lines* using *style*."""
    if style == "python":
        stripped = _strip_python_comments(code_lines)
    elif style == "c_style":
        stripped = _strip_c_style_comments(code_lines)
    elif style == "html":
        stripped = _strip_html_comments(code_lines)
    elif style == "sql":
        stripped = _strip_sql_comments(code_lines)
    else:
        stripped = _strip_c_style_comments(code_lines)
    return _compact_blank_lines(stripped)


# ---------------------------------------------------------------------------
# Fence parsing
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(r"^(`{3,}|~{3,})(.*)")


def _process_content(content: str) -> str:
    """Strip comments from fenced code blocks in *content*.

    Prose sections between (and around) code blocks are returned verbatim.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")
    result: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        m = _FENCE_RE.match(line)
        if m:
            fence_marker = m.group(1)
            lang = m.group(2).strip()
            fence_char = fence_marker[0]
            fence_len = len(fence_marker)
            style = _detect_comment_style(lang)

            # Collect lines until closing fence
            result.append(line)  # opening fence line preserved
            i += 1
            code_lines: list[str] = []
            while i < len(lines):
                cl = lines[i]
                stripped_cl = cl.strip()
                if (
                    all(c == fence_char for c in stripped_cl)
                    and len(stripped_cl) >= fence_len
                    and stripped_cl  # not empty
                ):
                    # Closing fence
                    stripped_code = _strip_comments_from_code(code_lines, style)
                    result.extend(stripped_code)
                    result.append(cl)  # closing fence preserved
                    i += 1
                    break
                code_lines.append(cl)
                i += 1
            else:
                # Unclosed fence — emit code lines as-is
                result.extend(code_lines)
        else:
            result.append(line)
            i += 1

    return "\n".join(result)


def _process_message_content(content: Any) -> Any:
    """Process content field of a message."""
    if content is None:
        return content
    if isinstance(content, str):
        return _process_content(content)
    if isinstance(content, list):
        processed = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                new_text = _process_content(part.get("text", ""))
                processed.append({**part, "text": new_text})
            else:
                processed.append(part)
        return processed
    return content


class CommentStripper:
    """Pruning transform that removes code comments from fenced code blocks.

    Prose content outside code blocks is left completely untouched.
    Applies to all message roles (system, user, assistant, tool).
    """

    def transform(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Return a deep copy of *request* with code comments stripped.

        Short-circuits (returns a deep copy unchanged) if no fenced code
        blocks are present anywhere in the request.
        """
        # Short-circuit: scan for any fenced block before doing work
        has_fence = False
        for msg in request.messages:
            content = msg.content
            if isinstance(content, str) and ("```" in content or "~~~" in content):
                has_fence = True
                break
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        t = part.get("text", "")
                        if "```" in t or "~~~" in t:
                            has_fence = True
                            break
                if has_fence:
                    break

        pruned = request.model_copy(deep=True)
        if not has_fence:
            return pruned

        new_messages: list[ChatMessage] = []
        for msg in pruned.messages:
            new_content = _process_message_content(msg.content)
            if new_content is not msg.content:
                msg = msg.model_copy(update={"content": new_content})
            new_messages.append(msg)
        pruned.messages = new_messages
        return pruned
