"""OpenAI-compatible provider adapter.

Forwards ``ChatCompletionRequest`` objects to any OpenAI-compatible HTTP
endpoint and streams raw SSE byte chunks back to the caller.

Error handling
--------------
- Connection errors (DNS, connection refused, etc.) → re-raised as
  ``httpx.ConnectError``; the global exception handler converts this to 502.
- Timeout → re-raised as ``httpx.TimeoutException``; the global exception
  handler converts this to 504.
- Upstream HTTP error status codes (4xx / 5xx) → re-raised as
  ``httpx.HTTPStatusError``; the global exception handler mirrors the upstream
  status and body back to the client.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

import httpx

from src.config import Settings
from src.models.chat import ChatCompletionRequest

logger = logging.getLogger(__name__)


class OpenAIProviderAdapter:
    """Adapter that targets any OpenAI-compatible ``/v1/chat/completions``
    endpoint.

    Parameters
    ----------
    settings:
        Application settings; used to read ``upstream_api_url``,
        ``upstream_api_key``, and ``upstream_timeout``.
    """

    def __init__(self, settings: Settings) -> None:
        self._upstream_url = settings.upstream_api_url
        self._api_key = settings.upstream_api_key
        self._timeout = settings.upstream_timeout

    async def stream_completions(
        self, request: ChatCompletionRequest
    ) -> AsyncIterator[bytes]:
        """Forward *request* to the upstream API and stream raw SSE bytes back.

        The method streams data line-by-line from the upstream response.  Each
        non-empty line is yielded as raw bytes so the chat router can forward it
        directly to the client without re-framing.

        Raises
        ------
        httpx.ConnectError
            When the upstream host cannot be reached.
        httpx.TimeoutException
            When the upstream does not respond within the configured timeout.
        httpx.HTTPStatusError
            When the upstream returns a 4xx or 5xx status code.
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if request.stream else "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        # Serialize request; include all extra fields for full pass-through
        payload = request.model_dump(exclude_none=True)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                self._upstream_url,
                headers=headers,
                content=json.dumps(payload),
            ) as response:
                # If the upstream returned an error, read the full body into memory
                # before raising. This ensures the global exception handler can
                # access response.text or response.json() even after the stream closes.
                if response.is_error:
                    await response.aread()
                
                # Raise immediately for non-2xx so exception handler can map
                # the status code to the correct HTTP error response
                response.raise_for_status()

                logger.debug(
                    "Upstream %s responded with status %d",
                    self._upstream_url,
                    response.status_code,
                )

                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
