"""Tests for src/cache/key_builder.py."""

from __future__ import annotations

import pytest

from src.cache.key_builder import CacheKeyBuilder, _DEFAULT_TEMP_BUCKET
from src.models.chat import ChatCompletionRequest, ChatMessage


def _make_request(
    messages: list[dict],
    model: str = "gpt-4o",
    temperature: float | None = 0.7,
) -> ChatCompletionRequest:
    return ChatCompletionRequest(
        model=model,
        messages=[ChatMessage(**m) for m in messages],
        temperature=temperature,
    )


class TestCacheKeyBuilder:
    @pytest.fixture
    def builder(self) -> CacheKeyBuilder:
        return CacheKeyBuilder()

    # ------------------------------------------------------------------
    # Standard request
    # ------------------------------------------------------------------

    def test_standard_request_builds_key(self, builder: CacheKeyBuilder) -> None:
        request = _make_request(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is recursion?"},
            ],
            model="gpt-4o",
            temperature=0.7,
        )
        key = builder.build(request, tenant_id="acme")

        assert key.tenant_id == "acme"
        assert key.model == "gpt-4o"
        assert key.temp_bucket == 7  # round(0.7 * 10)
        assert len(key.sys_prompt_hash) == 64  # SHA-256 hex
        assert len(key.ctx_hash) == 64

    # ------------------------------------------------------------------
    # No system message
    # ------------------------------------------------------------------

    def test_no_system_message_uses_empty_hash(self, builder: CacheKeyBuilder) -> None:
        request_no_sys = _make_request(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
        )
        request_with_sys = _make_request(
            messages=[
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "Hello"},
            ],
            temperature=0.5,
        )
        key_no_sys = builder.build(request_no_sys, tenant_id="t1")
        key_with_sys = builder.build(request_with_sys, tenant_id="t1")

        assert key_no_sys.sys_prompt_hash != key_with_sys.sys_prompt_hash

    # ------------------------------------------------------------------
    # Null temperature
    # ------------------------------------------------------------------

    def test_null_temperature_uses_default_bucket(self, builder: CacheKeyBuilder) -> None:
        request = _make_request(
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
        )
        key = builder.build(request, tenant_id="t1")
        assert key.temp_bucket == _DEFAULT_TEMP_BUCKET

    # ------------------------------------------------------------------
    # Temperature bucketing
    # ------------------------------------------------------------------

    def test_nearby_temperatures_get_same_bucket(self, builder: CacheKeyBuilder) -> None:
        r1 = _make_request([{"role": "user", "content": "hi"}], temperature=0.71)
        r2 = _make_request([{"role": "user", "content": "hi"}], temperature=0.69)
        k1 = builder.build(r1, "t1")
        k2 = builder.build(r2, "t1")
        assert k1.temp_bucket == k2.temp_bucket == 7

    def test_different_temperatures_get_different_buckets(self, builder: CacheKeyBuilder) -> None:
        r1 = _make_request([{"role": "user", "content": "hi"}], temperature=0.1)
        r2 = _make_request([{"role": "user", "content": "hi"}], temperature=0.9)
        k1 = builder.build(r1, "t1")
        k2 = builder.build(r2, "t1")
        assert k1.temp_bucket != k2.temp_bucket

    # ------------------------------------------------------------------
    # Tenant isolation
    # ------------------------------------------------------------------

    def test_different_tenants_produce_different_keys(self, builder: CacheKeyBuilder) -> None:
        request = _make_request([{"role": "user", "content": "hello"}])
        k1 = builder.build(request, tenant_id="acme")
        k2 = builder.build(request, tenant_id="beta")
        assert k1.tenant_id != k2.tenant_id
        # all other fields identical
        assert k1.sys_prompt_hash == k2.sys_prompt_hash
        assert k1.ctx_hash == k2.ctx_hash

    # ------------------------------------------------------------------
    # Context hash isolates conversation history
    # ------------------------------------------------------------------

    def test_different_conversation_context_produces_different_ctx_hash(
        self, builder: CacheKeyBuilder
    ) -> None:
        r1 = _make_request(
            messages=[
                {"role": "user", "content": "step 1"},
                {"role": "assistant", "content": "done"},
                {"role": "user", "content": "final question"},
            ]
        )
        r2 = _make_request(
            messages=[
                {"role": "user", "content": "final question"},
            ]
        )
        k1 = builder.build(r1, "t1")
        k2 = builder.build(r2, "t1")
        assert k1.ctx_hash != k2.ctx_hash

    # ------------------------------------------------------------------
    # last_user_text
    # ------------------------------------------------------------------

    def test_last_user_text_returns_last_user_message(self, builder: CacheKeyBuilder) -> None:
        request = _make_request(
            messages=[
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "reply"},
                {"role": "user", "content": "second"},
            ]
        )
        assert builder.last_user_text(request) == "second"

    def test_last_user_text_no_user_message_returns_empty(self, builder: CacheKeyBuilder) -> None:
        request = _make_request(messages=[{"role": "system", "content": "sys"}])
        assert builder.last_user_text(request) == ""
