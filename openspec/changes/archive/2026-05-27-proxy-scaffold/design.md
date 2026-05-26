## Context

The project ("Nexus") is a token-optimization gateway that sits between any OpenAI-compatible client and the upstream LLM API. Today there is no codebase — this is a greenfield scaffold. The gateway must be fully transparent: the client should not know it is talking to a proxy. All requests and responses, including streaming SSE, must pass through unmodified in this phase.

The upstream target is any OpenAI-compatible API (e.g., OpenAI, Anthropic via proxy, Azure OpenAI, or any custom LLM endpoint) that exposes `POST /v1/chat/completions`. The client sends an API key in the `Authorization` header; the gateway will use a prefix convention on this key to identify the tenant before forwarding.

## Goals / Non-Goals

**Goals:**
- Stand up a working FastAPI application that can receive, forward, and stream back OpenAI-compatible chat completion requests
- Validate that OpenAI-compatible requests (via curl, test scripts, or any client) work when pointed at `localhost:8000` with zero functional difference
- Establish the provider-adapter pattern so future providers can be added without touching the core proxy
- Extract tenant identity from every request for downstream per-tenant caching and routing
- Handle upstream failures gracefully — never swallow or reformat an error the client wouldn't otherwise see

**Non-Goals:**
- Caching, prompt pruning, or request modification (Phase 2–4)
- Multi-model routing or cost optimization logic (Phase 3)
- Telemetry / Prometheus metrics (Phase 5)
- Authentication or authorization beyond tenant extraction (future)
- Persistent storage or database setup
- Production deployment, Docker, or CI/CD pipeline

## Decisions

### 1. FastAPI + Uvicorn as the application stack
**Choice**: FastAPI with Uvicorn ASGI server.
**Rationale**: First-class async/await support is critical for non-blocking upstream HTTP calls and SSE streaming. FastAPI's Pydantic integration gives us request/response validation for free. Uvicorn provides production-grade ASGI serving.
**Alternatives considered**:
- *Flask + Gunicorn*: Synchronous by default; streaming SSE would require gevent or threading hacks.
- *aiohttp*: Capable but lacks built-in schema validation and OpenAPI docs.

### 2. httpx as the async HTTP client
**Choice**: `httpx` with `AsyncClient` for upstream calls.
**Rationale**: httpx is the de-facto async HTTP client for Python. It supports streaming responses natively (`aiter_lines()`), connection pooling, and timeout configuration. It mirrors the `requests` API, reducing cognitive overhead.
**Alternatives considered**:
- *aiohttp.ClientSession*: Viable but inconsistent API style with FastAPI's ecosystem.
- *requests + threading*: Blocks the event loop — unacceptable for a streaming proxy.

### 3. Server-Sent Events (SSE) Streaming
- **Choice:** FastAPI's native `StreamingResponse`.
- **Rationale:** Since the proxy's goal is strictly pass-through efficiency, and the upstream provider (OpenAI) already perfectly formats the SSE chunks (`data: {...}\n\n`), using `StreamingResponse` allows us to yield those raw bytes directly to the client with zero processing overhead. We evaluated `sse-starlette` initially, but it requires decoding the stream into objects only to re-encode them, which is unnecessarily inefficient for a transparent proxy.

### 4. Tenant extraction via API key prefix convention
**Choice**: Parse the API key from the `Authorization: Bearer <key>` header. The tenant ID is the segment before the first `_` delimiter (e.g., `tenant123_sk-abc...` → tenant `tenant123`). If no prefix is found, default to `default`.
**Rationale**: Zero-infrastructure tenant identification. No database lookup, no JWT decoding. The convention can be enforced at key-provisioning time. Future phases can upgrade to a proper auth system without changing the middleware contract.
**Alternatives considered**:
- *Custom header (`X-Tenant-ID`)*: Requires client modification — not transparent.
- *JWT claims*: Adds a verification dependency and key management before we have any infra.

### 5. Provider adapter pattern
**Choice**: Define a `ProviderAdapter` protocol (abstract base) with a `stream_completions(request) → AsyncIterator[bytes]` method. Implement a concrete `OpenAIProviderAdapter` that calls any OpenAI-compatible API.
**Rationale**: Decouples the proxy endpoint from any single upstream API. Adding a new provider (e.g., Anthropic native, custom endpoints) means implementing one new class — no changes to the router or middleware.

### 6. Application directory structure
```
src/
├── app.py                  # FastAPI app factory, middleware registration
├── config.py               # Settings via pydantic-settings (env vars)
├── models/
│   ├── __init__.py
│   └── chat.py             # OpenAI-compatible request/response Pydantic models
├── middleware/
│   ├── __init__.py
│   └── tenant.py           # Tenant extraction middleware
├── providers/
│   ├── __init__.py
│   ├── base.py             # ProviderAdapter protocol
│   └── openai.py           # OpenAI-compatible API adapter
├── routers/
│   ├── __init__.py
│   ├── chat.py             # POST /v1/chat/completions
│   └── health.py           # GET /health
└── exceptions.py           # Global exception handler
```

### 7. Global exception handling — fallback pass-through
**Choice**: Register a catch-all exception handler that, for upstream HTTP errors, mirrors the upstream status code and body back to the client. For unexpected internal errors, return a 502 Bad Gateway with a minimal JSON error body.
**Rationale**: The gateway must be invisible. If the upstream returns a 429 rate-limit, the client must see exactly that 429. Swallowing or rewriting errors would break client retry logic.

## Risks / Trade-offs

- **Single provider lock-in** → Mitigated by the adapter pattern; adding providers is a single-class change.
- **Tenant ID spoofing** → Accepted for Phase 1. No auth system exists yet; tenant extraction is for labeling, not access control. Mitigation deferred to a future auth phase.
- **SSE streaming fragility** → If the upstream sends malformed SSE or disconnects mid-stream, the proxy may leak the connection. Mitigated by setting httpx read timeouts and wrapping the stream iterator in a try/finally that closes the upstream response.
- **Performance overhead** → An extra network hop adds latency. Acceptable: the proxy is on localhost, adding < 1 ms. Future phases will more than offset this with caching.
- **No graceful shutdown** → Uvicorn handles SIGTERM, but in-flight streams may be interrupted. Acceptable for Phase 1; proper shutdown hooks are a future concern.
