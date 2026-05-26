"""OpenAI-compatible Pydantic models for chat completions.

These models mirror the OpenAI Chat Completions API schema so the gateway
can validate incoming requests and produce properly-structured responses
without losing any provider-specific extension fields.
"""

from __future__ import annotations

from typing import Any, Literal, Union, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Optional[Union[str, list[Any]]] = None
    name: Optional[str] = None
    tool_calls: Optional[list[Any]] = None
    tool_call_id: Optional[str] = None

    model_config = {"extra": "allow"}


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completions request body.

    Extra fields are preserved via ``extra="allow"`` so provider-specific
    extensions (e.g., Anthropic thinking tokens, Azure deployment IDs) are
    forwarded to the upstream without loss.
    """

    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = None
    max_tokens: int = None
    top_p: float = None
    stop: Union[str, list[str]] = None
    n: int = None
    frequency_penalty: float = None
    presence_penalty: float = None
    user: str = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Non-streaming response models
# ---------------------------------------------------------------------------


class ChatChoiceMessage(BaseModel):
    role: str
    content: str = None
    tool_calls: list[Any] = None

    model_config = {"extra": "allow"}


class ChatChoice(BaseModel):
    index: int
    message: ChatChoiceMessage
    finish_reason: str = None
    logprobs: Any = None

    model_config = {"extra": "allow"}


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    model_config = {"extra": "allow"}


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible non-streaming chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatChoice]
    usage: UsageInfo = None
    system_fingerprint: str = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Streaming response models (SSE delta chunks)
# ---------------------------------------------------------------------------


class ChatDelta(BaseModel):
    """Incremental token delta inside a streaming chunk."""

    role: str = None
    content: str = None
    tool_calls: list[Any] = None

    model_config = {"extra": "allow"}


class ChatChunkChoice(BaseModel):
    index: int
    delta: ChatDelta
    finish_reason: str = None
    logprobs: Any = None

    model_config = {"extra": "allow"}


class ChatCompletionChunk(BaseModel):
    """OpenAI-compatible streaming SSE chunk (``data: {...}`` lines)."""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatChunkChoice]
    system_fingerprint: str = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Error response model
# ---------------------------------------------------------------------------


class GatewayErrorDetail(BaseModel):
    message: str
    type: str = "gateway_error"
    code: str = None


class GatewayErrorResponse(BaseModel):
    error: GatewayErrorDetail = Field(...)
