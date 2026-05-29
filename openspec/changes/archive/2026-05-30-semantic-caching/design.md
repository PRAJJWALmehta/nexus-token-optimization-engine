## Context

The Nexus gateway currently proxies every `POST /v1/chat/completions` request straight to the upstream LLM provider. There is no request deduplication — identical or near-identical prompts generate full upstream round-trips each time, costing real tokens and introducing unnecessary latency. The existing architecture is a clean FastAPI pipeline: tenant middleware → chat router → provider adapter, with streaming SSE pass-through. This design adds a caching layer that intercepts requests _between_ the router and the provider, without altering the existing contract.

## Goals / Non-Goals

**Goals:**
- Intercept semantically duplicate requests before they reach the upstream provider and serve cached responses with sub-50ms latency.
- Achieve tenant-isolated caching — one tenant's cache MUST NOT leak into another's results.
- Maintain full OpenAI API compatibility — cached responses are indistinguishable from live upstream responses (same SSE format, same headers, same JSON schema).
- Support both streaming (`stream: true`) and non-streaming request/response caching.
- Provide observability via `X-Cache: HIT`/`MISS` response headers.

**Non-Goals:**
- Semantic similarity across _different_ conversation contexts (e.g., cross-conversation dedup). We only cache exact-context matches with semantic similarity on the final user message.
- Cache invalidation via API (no explicit purge endpoint in this phase).
- Distributed embedding inference — the model runs in-process, single-node only.
- Caching tool-call / function-call responses (these are non-deterministic by nature).
- Cache analytics dashboard or admin UI.

## Decisions

### 1. Embedding Model: `all-MiniLM-L6-v2` via `sentence-transformers`

**Choice**: Local in-process embedding using `sentence-transformers` with the `all-MiniLM-L6-v2` model (384 dimensions, ~80MB).

**Alternatives considered**:
- *OpenAI `text-embedding-3-small`*: Higher quality but adds an external API call per request (~50ms + cost). Defeats the purpose of reducing upstream calls.
- *`all-mpnet-base-v2`*: Better accuracy (768 dims) but 2× the memory and index size. MiniLM is sufficient for detecting near-identical prompts.
- *TF-IDF / bag-of-words hashing*: Zero ML dependency but cannot detect paraphrases. The whole value of semantic caching is catching semantically equivalent but lexically different queries.

**Rationale**: MiniLM gives us paraphrase detection with ~5ms encode latency, zero network cost, and a small memory footprint. The model is loaded once at startup and shared across requests.

### 2. Vector Store: Redis + RediSearch (HNSW index)

**Choice**: Redis 7+ with the RediSearch module for vector similarity search using an HNSW index.

**Alternatives considered**:
- *Pinecone / Weaviate / Qdrant (managed)*: Overkill for a gateway cache. Adds infrastructure cost, latency, and vendor lock-in.
- *ChromaDB (embedded)*: Python-native but lacks production features (TTL, persistence, atomic operations). No built-in metadata filtering.
- *In-memory dict with NumPy cosine similarity*: Fastest for small scale, but no persistence across restarts, no TTL, no tenant-scoped filtering without full scan.

**Rationale**: Redis is already a common infra component. RediSearch provides native vector similarity + metadata filtering (tenant scoping) in a single query. HNSW gives us O(log n) lookups. Built-in TTL via `EXPIRE` handles cache eviction for free.

### 3. Cache Key Composition: Composite hash for isolation

**Structure**: Each cached entry is keyed by a composite of:
| Component | Purpose |
|---|---|
| `tenant_id` | Tenant isolation — enforced via RediSearch filter |
| `sys_prompt_hash` | SHA-256 of concatenated system messages — different system prompts = different cache partitions |
| `model` | Model name — responses from GPT-4o ≠ responses from GPT-3.5 |
| `temp_bucket` | `round(temperature * 10)` — groups nearby temperatures (0.71 and 0.69 → same bucket 7) |
| `ctx_hash` | SHA-256 of the full message history (excluding last user message) — prevents false hits when conversation context differs |

**Vector**: The embedding of the _last user message_ only. This is the semantic search target.

**Rationale**: The vector captures semantic meaning; the composite hash captures _context_. Two users asking "explain recursion" get a HIT only if they also share the same system prompt, model, temperature range, and conversation history. This prevents subtle but dangerous false positives.

### 4. Cache Lookup Flow

```
Request in → embed(last_user_msg) → RediSearch ANN query
  → filter: tenant_id AND sys_prompt_hash AND model AND temp_bucket
  → top-1 result where similarity ≥ threshold
  → verify: result.ctx_hash == request.ctx_hash
  → HIT: replay cached response
  → MISS: forward to upstream, buffer response, store in cache
```

**Similarity threshold**: Configurable, default `0.95`. High threshold minimizes false positives.

### 5. Response Buffering Strategy

**For streaming responses (cache misses)**:
- The `StreamBuffer` wraps the provider's async iterator.
- It yields each chunk to the client in real-time (no added latency) while accumulating the raw SSE bytes in memory.
- On stream completion (after `data: [DONE]`), the buffer persists the full response + metadata to Redis asynchronously via `asyncio.create_task`.

**For non-streaming responses**: The JSON response body is stored directly after the upstream call returns.

**Rationale**: Buffering is transparent to the client — they see exactly the same streaming behavior. The cache write happens _after_ the response is fully delivered, so it never adds latency to the request path.

### 6. Synthetic SSE Replay on Cache Hit

On a cache hit for a streaming request, the cached response bytes are re-streamed as SSE chunks with small inter-chunk delays (~1ms) to simulate realistic streaming cadence. This ensures client-side SSE parsers behave identically to a live upstream response.

For non-streaming cache hits, the stored JSON is returned directly as a `JSONResponse`.

### 7. Module Structure

```
src/cache/
├── __init__.py
├── embedder.py          # EmbeddingEngine: wraps sentence-transformers model
├── key_builder.py       # CacheKeyBuilder: composite hash construction
├── store.py             # RedisCacheStore: Redis + RediSearch operations
├── lookup.py            # CacheLookup: orchestrates embed → search → verify
├── buffer.py            # StreamBuffer: intercepts SSE stream for caching
└── replay.py            # CacheReplay: synthetic SSE re-streaming
```

The chat router imports `CacheLookup` and `StreamBuffer` — the only two touch-points with existing code.

### 8. Graceful Degradation

If Redis is unavailable or the embedding model fails to load, caching degrades gracefully:
- The gateway logs a warning and continues proxying all requests directly to upstream.
- A `cache_enabled` flag in settings provides a hard kill-switch.
- Redis connection failures are caught per-request — a transient Redis outage doesn't crash the gateway.

## Risks / Trade-offs

| Risk | Mitigation |
|---|---|
| **False positive cache hits** (different intent, same embedding) | Context hash verification as second gate; high similarity threshold (0.95); tenant + model + temp scoping |
| **Memory pressure** from `sentence-transformers` model (~80MB) | Acceptable for a gateway process; model is loaded once, shared across requests |
| **Redis dependency** — new infra requirement | Graceful degradation: if Redis is down, all requests pass through. No hard dependency. |
| **Cache staleness** — upstream model behavior changes | TTL-based expiry (default 1h); no indefinite caching. Future: explicit invalidation API. |
| **Embedding latency** on hot path (~5ms per request) | Async embedding; MiniLM is fast enough to stay under the noise floor of upstream latency (1-10s) |
| **Large cached responses** consuming Redis memory | Max response size limit (configurable, default 512KB); Redis memory policy eviction as backstop |
