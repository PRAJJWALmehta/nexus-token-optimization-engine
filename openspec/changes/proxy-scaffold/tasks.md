## 1. Project Setup

- [ ] 1.1 Initialize Python project with `pyproject.toml` (or `requirements.txt`): `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pydantic-settings`, `sse-starlette`
- [ ] 1.2 Create the `src/` directory structure per design (`app.py`, `config.py`, `models/`, `middleware/`, `providers/`, `routers/`, `exceptions.py`)
- [ ] 1.3 Create `src/config.py` with `Settings` class using `pydantic-settings` (env vars: `UPSTREAM_API_URL`, `UPSTREAM_TIMEOUT`, `HOST`, `PORT`)

## 2. Pydantic Models

- [ ] 2.1 Create `src/models/chat.py` with `ChatMessage`, `ChatCompletionRequest` (model, messages, stream, temperature, max_tokens, top_p, stop, n — extra fields allowed via `model_config`)
- [ ] 2.2 Add `ChatCompletionResponse` and `ChatCompletionChunk` (streaming delta) models to `src/models/chat.py`

## 3. Tenant Extraction Middleware

- [ ] 3.1 Create `src/middleware/tenant.py` implementing ASGI middleware that parses `Authorization: Bearer <key>`, extracts tenant ID from key prefix (before first `_`), defaults to `"default"`, and sets `request.state.tenant_id`

## 4. Provider Adapter

- [ ] 4.1 Create `src/providers/base.py` with `ProviderAdapter` abstract base class defining `async stream_completions(request) → AsyncIterator[bytes]`
- [ ] 4.2 Create `src/providers/openai.py` with `OpenAIProviderAdapter` that uses `httpx.AsyncClient` to POST to the upstream URL, stream SSE lines, and yield raw bytes
- [ ] 4.3 Handle upstream connection failures (raise exception → 502) and timeouts (raise exception → 504) in the adapter

## 5. Route Handlers

- [ ] 5.1 Create `src/routers/health.py` with `GET /health` returning `{"status": "healthy"}` (200 OK, no I/O)
- [ ] 5.2 Create `src/routers/chat.py` with `POST /v1/chat/completions` — accept `ChatCompletionRequest`, call `provider.stream_completions()`, return `EventSourceResponse` for streaming or JSON for non-streaming

## 6. Exception Handling

- [ ] 6.1 Create `src/exceptions.py` with a global exception handler: upstream HTTP errors pass through status + body; unhandled errors return 502 with `{"error": {"message": "...", "type": "gateway_error"}}`
- [ ] 6.2 Register the exception handler in the FastAPI app

## 7. Application Wiring

- [ ] 7.1 Create `src/app.py` with FastAPI app factory: register middleware, include routers, attach exception handlers, instantiate provider adapter from config
- [ ] 7.2 Add `__main__.py` or entrypoint to run `uvicorn src.app:app` with configurable host/port

## 8. Integration Test

- [ ] 8.1 Manual end-to-end test: start the gateway on `localhost:8000`, send an OpenAI-compatible chat request via `curl` or a test script, confirm the response streams back correctly from the configured upstream
- [ ] 8.2 Verify `/health` returns 200 with `{"status": "healthy"}`
- [ ] 8.3 Verify upstream errors (e.g., invalid API key → 401) are passed through unchanged
