"""Unit tests for ComplexityClassifier.

Covers all spec scenarios:
- Low complexity by token count
- High complexity by token count
- High complexity by keyword (whole-word)
- Keyword does NOT match partial words (e.g., "refactoring")
- Empty / null content handling
- No user message defaults to LOW
- Multimodal content extraction
- System message keyword detection
- Assistant messages excluded from analysis
- Custom keyword configuration
- Custom token threshold
"""

from __future__ import annotations

import pytest

from src.models.chat import ChatCompletionRequest, ChatMessage
from src.routing.classifier import ComplexityClassifier, ComplexityLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(*messages: dict) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model="auto",
        messages=[ChatMessage(**m) for m in messages],
    )


def _user(content: str) -> dict:
    return {"role": "user", "content": content}


def _system(content: str) -> dict:
    return {"role": "system", "content": content}


def _assistant(content: str) -> dict:
    return {"role": "assistant", "content": content}


# ---------------------------------------------------------------------------
# Default classifier fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def clf() -> ComplexityClassifier:
    return ComplexityClassifier()


# ---------------------------------------------------------------------------
# Token count signal
# ---------------------------------------------------------------------------


class TestTokenCountSignal:
    def test_short_request_is_low(self, clf: ComplexityClassifier):
        """A simple short prompt with no keywords is classified LOW."""
        req = _make_request(_user("Format this JSON: {}"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW
        assert result.keyword_match is None

    def test_at_threshold_is_high(self):
        """Estimated tokens == threshold → HIGH (>= comparison)."""
        # threshold=100, message of 400 chars → 100 tokens
        clf = ComplexityClassifier(token_threshold=100)
        content = "x" * 400  # 400 chars // 4 = 100 tokens
        req = _make_request(_user(content))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH
        assert result.tokens_est == 100

    def test_above_threshold_is_high(self):
        """Tokens well above threshold → HIGH."""
        clf = ComplexityClassifier(token_threshold=100)
        content = "y" * 800  # 800 // 4 = 200 tokens
        req = _make_request(_user(content))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH

    def test_below_threshold_with_no_keywords_is_low(self):
        """Tokens below threshold and no keywords → LOW."""
        clf = ComplexityClassifier(token_threshold=100)
        content = "z" * 100  # 100 // 4 = 25 tokens
        req = _make_request(_user(content))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW

    def test_tokens_est_reported_correctly(self, clf: ComplexityClassifier):
        """tokens_est in result equals len(text) // 4."""
        content = "a" * 80  # 80 // 4 = 20 tokens
        req = _make_request(_user(content))
        result = clf.classify(req)
        assert result.tokens_est == 20


# ---------------------------------------------------------------------------
# Keyword signal
# ---------------------------------------------------------------------------


class TestKeywordSignal:
    def test_keyword_match_is_high(self, clf: ComplexityClassifier):
        """Request containing a complexity keyword → HIGH."""
        req = _make_request(_user("Refactor this architecture for better scalability"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH
        assert result.keyword_match is not None

    def test_keyword_match_is_case_insensitive(self, clf: ComplexityClassifier):
        """Keyword matching is case-insensitive."""
        for variant in ["REFACTOR", "Refactor", "rEfAcToR"]:
            req = _make_request(_user(f"Please {variant} this code"))
            result = clf.classify(req)
            assert result.level == ComplexityLevel.HIGH, (
                f"Expected HIGH for keyword variant '{variant}'"
            )

    def test_partial_word_does_not_match(self, clf: ComplexityClassifier):
        """'refactoring' must NOT trigger the 'refactor' keyword (whole-word)."""
        req = _make_request(_user("I am refactoring this file gradually"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW, (
            "Partial word 'refactoring' should NOT match keyword 'refactor'"
        )

    def test_partial_word_refactored_does_not_match(self, clf: ComplexityClassifier):
        """'refactored' must NOT trigger the 'refactor' keyword."""
        req = _make_request(_user("I already refactored this module"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW

    def test_multiple_keywords_returns_first(self, clf: ComplexityClassifier):
        """When multiple keywords present, first matched is reported."""
        req = _make_request(_user("Please refactor and optimize this code"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH
        assert result.keyword_match is not None

    def test_keyword_reported_in_result(self, clf: ComplexityClassifier):
        """keyword_match field contains the matched keyword string."""
        req = _make_request(_user("Please analyze the performance"))
        result = clf.classify(req)
        assert result.keyword_match == "analyze"

    def test_keyword_overrides_short_token_count(self, clf: ComplexityClassifier):
        """Even a very short request is HIGH if a keyword is present."""
        req = _make_request(_user("Debug this"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH


# ---------------------------------------------------------------------------
# Message scope
# ---------------------------------------------------------------------------


class TestMessageScope:
    def test_system_message_keyword_triggers_high(self, clf: ComplexityClassifier):
        """Keywords in system messages trigger HIGH."""
        req = _make_request(
            _system("You are a senior architect. Analyze deeply."),
            _user("Sure, go ahead."),
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH

    def test_assistant_message_keyword_excluded(self, clf: ComplexityClassifier):
        """Keywords in assistant messages must NOT trigger HIGH."""
        req = _make_request(
            _user("How are you?"),
            _assistant("Let me refactor this for you."),  # should be ignored
            _user("Thanks."),
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW, (
            "Assistant message keyword 'refactor' should not influence classification"
        )

    def test_only_last_user_message_scanned(self, clf: ComplexityClassifier):
        """Only the LAST user message is scanned; earlier user messages are excluded."""
        req = _make_request(
            _user("Refactor the whole system"),  # earlier — should be ignored
            _assistant("OK, I will help."),
            _user("Never mind, just format this JSON."),  # last — no keyword
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW, (
            "Earlier user message keyword should not be counted"
        )

    def test_tool_message_excluded(self, clf: ComplexityClassifier):
        """Tool/function messages are excluded from analysis."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(role="system", content="You are helpful."),
                ChatMessage(role="user", content="Call the tool."),
                ChatMessage(role="tool", content="Refactor result", tool_call_id="1"),
            ],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_null_content_treated_as_zero(self, clf: ComplexityClassifier):
        """Messages with None content contribute zero tokens and no matches."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(role="system", content=None),
                ChatMessage(role="user", content=None),
            ],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW
        assert result.tokens_est == 0

    def test_empty_string_content(self, clf: ComplexityClassifier):
        """Empty-string content contributes zero tokens."""
        req = _make_request(_system(""), _user(""))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW
        assert result.tokens_est == 0

    def test_no_user_message_defaults_to_low(self, clf: ComplexityClassifier):
        """Request with only system messages defaults to LOW (no user message)."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[ChatMessage(role="system", content="You are helpful.")],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW

    def test_no_user_message_with_system_keyword_is_high(self, clf: ComplexityClassifier):
        """No user message but system keyword → HIGH (system is still scanned)."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(role="system", content="You are an expert architect.")
            ],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH


# ---------------------------------------------------------------------------
# Multimodal content
# ---------------------------------------------------------------------------


class TestMultimodalContent:
    def test_text_parts_extracted(self, clf: ComplexityClassifier):
        """Text parts from multimodal content are extracted and analysed."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": "Please refactor this code"},
                        {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
                    ],
                )
            ],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH, (
            "Text part with 'refactor' should trigger HIGH"
        )

    def test_image_parts_ignored(self, clf: ComplexityClassifier):
        """Image URL parts are silently ignored — no error, no keyword match."""
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "image_url", "image_url": {"url": "http://example.com/img.png"}},
                    ],
                )
            ],
        )
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW
        assert result.tokens_est == 0

    def test_mixed_multimodal_token_count(self, clf: ComplexityClassifier):
        """Token count sums only text parts, not image parts."""
        text_content = "a" * 80
        req = ChatCompletionRequest(
            model="auto",
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": text_content},
                        {"type": "image_url", "image_url": {"url": "http://x.com/img.png"}},
                    ],
                )
            ],
        )
        result = clf.classify(req)
        assert result.tokens_est == 20  # 80 // 4


# ---------------------------------------------------------------------------
# Configurable keywords and threshold
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_custom_keywords(self):
        """Custom keyword list replaces defaults."""
        clf = ComplexityClassifier(keywords=["migrate", "overhaul"])
        # "refactor" is in defaults but NOT in custom list → should be LOW
        req = _make_request(_user("Please refactor this"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW, (
            "'refactor' should not match when custom keywords don't include it"
        )
        # "migrate" IS in custom list → HIGH
        req2 = _make_request(_user("Please migrate this database"))
        result2 = clf.classify(req2)
        assert result2.level == ComplexityLevel.HIGH

    def test_custom_threshold(self):
        """Custom threshold changes the token boundary."""
        clf = ComplexityClassifier(token_threshold=50)
        # 50 * 4 = 200 chars → should be HIGH with threshold=50
        req = _make_request(_user("x" * 200))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.HIGH

    def test_custom_threshold_below_does_not_trigger(self):
        """Content below custom threshold stays LOW."""
        clf = ComplexityClassifier(token_threshold=1000)
        req = _make_request(_user("Hello world"))
        result = clf.classify(req)
        assert result.level == ComplexityLevel.LOW
