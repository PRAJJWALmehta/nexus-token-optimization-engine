# Master Implementation Plan: Nexus

This checklist breaks down the Master PRD into small, testable OpenSpec changes. Each phase is an independent `opsx-propose` → `opsx-apply` → `opsx-archive` cycle.

## Phase 1: Core Proxy Gateway 🌐
**Goal**: A functional pass-through proxy. Proves the gateway works end-to-end.

- [ ] **Change**: `proxy-scaffold`
  - FastAPI scaffold with `POST /v1/chat/completions`
  - OpenAI-compatible request/response Pydantic models
  - Tenant ID extraction middleware (from API key prefix)
  - OpenAI-compatible upstream provider adapter (streaming SSE pass-through)
  - `/health` endpoint
  - Global exception handler (fallback pass-through)
  - **Test**: Send OpenAI-compatible requests via `curl` or a test script to `localhost:8000`, confirm requests proxy through to the configured upstream and responses stream back.

## Phase 2: Semantic Caching 🧠
**Goal**: Cache duplicate queries. Biggest ROI.

- [ ] **Change**: `semantic-caching`
  - `all-MiniLM-L6-v2` local embedding engine (embed last user message)
  - Redis with RediSearch vector index
  - Cache key builder (tenant_id + sys_prompt_hash + model + temp_bucket + ctx_hash)
  - Semantic cache lookup (embed → filtered ANN → context_hash verify)
  - Streamed response buffering + cache store on completion
  - Synthetic SSE re-streaming on cache hit
  - **Test**: Send the same prompt twice, verify second response is a cache hit with near-zero latency.

## Phase 3: Dynamic Routing 🔀
**Goal**: Cost optimization via intelligent model selection.

- [ ] **Change**: `dynamic-routing`
  - Heuristic complexity classifier (token count + keyword signals)
  - Model routing logic (< 2000 tokens → Sonnet, ≥ 2000 → Opus)
  - Configurable routing rules via env vars
  - **Test**: "Format this JSON" → routes to Sonnet. "Refactor this architecture" → routes to Opus.

## Phase 4: Prompt Pruning 🗜️
**Goal**: Token reduction without ML. Fast, deterministic.

- [ ] **Change**: `prompt-pruning`
  - Whitespace normalization
  - Code comment stripping from content blocks
  - Duplicate system instruction deduplication
  - Token-budget-aware conversation truncation
  - Pruning pipeline orchestrator
  - **Test**: Send bloated prompt, verify token count reduced by 20%+ in forwarded request.

## Phase 5: Telemetry & Observability 📊
**Goal**: Measure cost savings, latency, and cache hit rates.

- [ ] **Change**: `telemetry-instrumentation`
  - Prometheus counters: `cache_hits_total`, `cache_misses_total`, `tokens_saved_total`
  - Prometheus histograms: `gateway_latency_seconds`, `provider_latency_seconds`
  - Routing distribution gauge: requests per model
  - `/metrics` scrape endpoint
  - **Test**: Generate traffic, scrape `/metrics`, verify counters increment correctly.

## Phase 6: AST Extraction 🌳 (Future)
**Goal**: Deterministic codebase parsing. Deferred until core layers are stable.

- [ ] **Change**: `ast-extractor`
  - Tree-sitter bindings (Python, TypeScript)
  - AST extraction (functions, classes, imports)
  - Local dependency graph storage (Graphify)
  - Graph query endpoint

---

### Workflow Process
For each change above:
1. `/opsx-propose <change-name>` — generate design and specs for that slice
2. `/opsx-apply` — implement and test the code
3. `/opsx-archive` — finalize the change and merge specs
