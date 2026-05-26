## Why

LLM-powered IDE tools (like Antigravity) send every chat and completion request directly to the upstream API with no opportunity for cost optimization. There is no intermediary to cache repeated prompts, prune redundant tokens, or route requests to cheaper models when appropriate. A transparent reverse-proxy gateway is the prerequisite for every downstream optimization — without it, caching, pruning, and routing have nowhere to live.

Building this first proves the end-to-end plumbing works (request in → upstream call → streamed response back) before any optimization logic is layered on.

## What Changes

- New FastAPI application (`POST /v1/chat/completions`) acting as an OpenAI-compatible reverse proxy
- Pydantic request/response models mirroring the OpenAI Chat Completions API (including streaming deltas)
- Tenant identification middleware that extracts a tenant ID from an API key prefix
- OpenAI-compatible upstream provider adapter that forwards requests and streams SSE responses back to the caller
- `/health` liveness endpoint for readiness checks
- Global exception handler ensuring upstream errors are forwarded transparently (fallback pass-through)

## Capabilities

### New Capabilities
- `chat-proxy`: OpenAI-compatible chat completions proxy endpoint with streaming SSE pass-through
- `tenant-extraction`: Middleware to derive tenant identity from API key prefix
- `provider-adapter`: Pluggable provider adapter interface with OpenAI-compatible upstream implementation
- `health-check`: Liveness/readiness endpoint for operational monitoring

### Modified Capabilities
_None — this is a greenfield scaffold._

## Impact

- **New code**: Entire `src/` application tree (FastAPI app, models, middleware, provider adapter)
- **APIs**: Exposes `POST /v1/chat/completions` and `GET /health` on localhost
- **Dependencies**: `fastapi`, `uvicorn`, `httpx` (async HTTP client for upstream calls), `pydantic`, `sse-starlette`
- **Systems**: Any OpenAI-compatible client (curl, test scripts, or IDE tools) can target `localhost:8000` as the API endpoint
