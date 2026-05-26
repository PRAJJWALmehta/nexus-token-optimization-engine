"""Chat completions router.

Exposes ``POST /v1/chat/completions`` which accepts OpenAI-compatible requests
and streams back responses from the configured upstream provider.
"""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from src.config import Settings, settings
from src.models.chat import ChatCompletionRequest
from src.providers.base import ProviderAdapter
from src.providers.openai import OpenAIProviderAdapter

router = APIRouter(tags=["chat"])

# Dependency to inject the configured provider adapter
def get_provider() -> ProviderAdapter:
    # In a more complex app, this could be instantiated dynamically
    # based on the requested model or tenant configuration.
    return OpenAIProviderAdapter(settings)


@router.post("/v1/chat/completions")
async def chat_completions(
    request_data: ChatCompletionRequest,
    request: Request,
    provider: Annotated[ProviderAdapter, Depends(get_provider)],
):
    """Proxy chat completions to the upstream LLM provider.

    Accepts an OpenAI-compatible request body. If ``stream=True``, streams
    the response chunks back to the client as Server-Sent Events (SSE).
    Otherwise, returns the complete JSON response.
    """
    # Note: Tenant ID is available here via request.state.tenant_id
    # tenant_id = getattr(request.state, "tenant_id", "default")

    if request_data.stream:
        # Pass through the raw bytes from the upstream provider.
        # Since the OpenAIProviderAdapter yields raw SSE-formatted bytes,
        # we can use standard StreamingResponse.
        return StreamingResponse(
            provider.stream_completions(request_data),
            media_type="text/event-stream",
        )
    else:
        # For non-streaming requests, we collect the chunks (which is just
        # the JSON response in a single chunk usually, or we can just proxy it).
        # Since our adapter is built for streaming, let's collect the bytes
        # and parse it back to JSON to return a proper JSONResponse.
        # Ideally, a non-streaming adapter method should exist, but for
        # simplicity, we read the stream and return it.
        chunks = []
        async for chunk in provider.stream_completions(request_data):
            chunks.append(chunk)
        
        body = b"".join(chunks)
        # Parse it as JSON and return using JSONResponse to ensure proper
        # Content-Type and formatting.
        return JSONResponse(content=json.loads(body))
