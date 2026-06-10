"""Whitespace normalizer for prompt pruning.

Collapses redundant whitespace in :class:`~src.models.chat.ChatCompletionRequest`
message content while preserving the internal formatting of fenced code blocks.

Rules applied outside fenced code blocks
-----------------------------------------
* Normalise line endings to ``\\n`` (strips ``\\r``).
* Strip trailing whitespace from every line.
* Collapse runs of two or more consecutive spaces/tabs inside a line to a
  single space.  Leading whitespace (indentation) is preserved.
* Collapse three or more consecutive blank lines down to two.

Code block preservation
------------------------
Content inside fenced code blocks (delimited by `` ``` `` or ``~~~``) is
passed through verbatim.  Only the *prose* segments between blocks are
normalised.

Multimodal content
-------------------
When a message ``content`` field is a list of content parts, normalisation is
applied to ``{"type": "text", "text": "..."}`` parts only.  Non-text parts
(e.g. ``image_url``) are passed through unchanged.
"""

from __future__ import annotations

import re
from typing import Any

from src.models.chat import ChatCompletionRequest, ChatMessage

# Matches the opening and closing fence lines: ```lang or ~~~
_FENCE_OPEN = re.compile(r"^(`{3,}|~{3,})(.*)", re.MULTILINE)


def _normalise_prose(text: str) -> str:
    """Normalise whitespace in a prose (non-code-block) segment."""
    # 1. Normalise CRLF / CR → LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines: list[str] = []
    for line in text.split("\n"):
        # 2. Strip trailing whitespace per line
        line = line.rstrip()
        # 3. Collapse runs of spaces/tabs *after* the leading whitespace
        leading = len(line) - len(line.lstrip())
        prefix = line[:leading]
        rest = line[leading:]
        rest = re.sub(r"[ \t]{2,}", " ", rest)
        lines.append(prefix + rest)

    # 4. Collapse 3+ consecutive blank lines → 2 blank lines
    result: list[str] = []
    blank_run = 0
    for line in lines:
        if line == "":
            blank_run += 1
            if blank_run <= 2:
                result.append(line)
        else:
            blank_run = 0
            result.append(line)

    return "\n".join(result)


def _normalise_content(content: str) -> str:
    """Normalise *content*, preserving fenced code blocks verbatim.

    Splits the content into alternating prose / code-block segments.
    Prose segments are normalised; code block segments are returned as-is.
    """
    segments: list[str] = []
    pos = 0
    text = content

    # Normalise line endings globally first so fence detection is reliable
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    i = 0
    lines = text.split("\n")
    prose_lines: list[str] = []
    inside_fence = False
    fence_char: str = ""
    fence_lines: list[str] = []

    for line in lines:
        if not inside_fence:
            m = _FENCE_OPEN.match(line)
            if m and m.group(1)[0] in ("`", "~"):
                # Flush accumulated prose
                segments.append(_normalise_prose("\n".join(prose_lines)))
                prose_lines = []
                # Start code block
                inside_fence = True
                fence_char = m.group(1)[0]
                fence_min_len = len(m.group(1))
                fence_lines = [line]
            else:
                prose_lines.append(line)
        else:
            fence_lines.append(line)
            # Closing fence: same char, equal-or-longer length, no info string
            stripped = line.strip()
            if (
                stripped
                and all(c == fence_char for c in stripped)
                and len(stripped) >= fence_min_len
            ):
                # End of code block — emit verbatim
                segments.append("\n".join(fence_lines))
                fence_lines = []
                inside_fence = False

    # Remaining content after last fence
    if inside_fence:
        # Unclosed fence — treat remaining as prose
        prose_lines.extend(fence_lines)
    if prose_lines:
        segments.append(_normalise_prose("\n".join(prose_lines)))

    return "\n".join(segments)


def _normalise_message_content(content: Any) -> Any:
    """Normalise the ``content`` field of a single :class:`ChatMessage`."""
    if content is None:
        return content
    if isinstance(content, str):
        return _normalise_content(content)
    if isinstance(content, list):
        result = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                new_text = _normalise_content(part.get("text", ""))
                result.append({**part, "text": new_text})
            else:
                result.append(part)
        return result
    return content


class WhitespaceNormalizer:
    """Pruning transform that normalises whitespace in message content.

    Applies to all message roles (system, user, assistant, tool).
    Fenced code blocks are preserved verbatim.
    """

    def transform(self, request: ChatCompletionRequest) -> ChatCompletionRequest:
        """Return a deep copy of *request* with normalised whitespace.

        Parameters
        ----------
        request:
            The incoming chat completion request to normalise.

        Returns
        -------
        ChatCompletionRequest
            A new request object with whitespace-normalised message content.
        """
        pruned = request.model_copy(deep=True)
        new_messages: list[ChatMessage] = []
        for msg in pruned.messages:
            normalised = _normalise_message_content(msg.content)
            if normalised is not msg.content:
                msg = msg.model_copy(update={"content": normalised})
            new_messages.append(msg)
        pruned.messages = new_messages
        return pruned
