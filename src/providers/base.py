"""Provider adapter protocol (abstract base).

All upstream LLM provider implementations must conform to this protocol.
Keeping the contract minimal (a single ``stream_completions`` method) means
adding a new provider is a single-class change with no impact on the router
or middleware layers.
"""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from src.models.chat import ChatCompletionRequest


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol that all provider adapters must implement.

    Parameters
    ----------
    request:
        The validated, OpenAI-compatible chat completion request.

    Yields
    ------
    bytes
        Raw SSE byte chunks as received from the upstream provider,
        forwarded verbatim to the client.
    """

    async def stream_completions(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[bytes]:
        ...
