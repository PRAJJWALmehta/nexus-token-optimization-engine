## Why

Every request that hits the gateway currently makes a full upstream LLM API call, even when an identical (or near-identical) query was answered seconds ago. For agentic coding workflows — where tools frequently re-submit the same prompt with minor whitespace/formatting variance — this duplication accounts for significant wasted cost and latency. Semantic caching intercepts these duplicate queries before they leave the gateway, serving cached responses with near-zero latency and zero token spend. This is the single highest-ROI optimization in the pipeline.

## What Changes

- **Embedding engine**: Introduce `all-MiniLM-L6-v2` via `sentence-transformers` to embed the last user message from each request into a 384-dimensional vector, running locally (no external API calls).
- **Redis vector store**: Use Redis with the RediSearch module to store and query cached response vectors using a FLAT or HNSW vector index.
- **Cache key builder**: Construct composite cache keys from `tenant_id`, a hash of the system prompt, the requested `model`, a bucketed `temperature` value, and a hash of the full conversation context — ensuring cache isolation across tenants and semantically distinct conversations.
- **Semantic cache lookup**: On each inbound request, embed the last user message, perform a filtered approximate-nearest-neighbor (ANN) search scoped to the tenant's cache partition, then verify the top candidate via a context hash equality check to prevent false-positive hits.
- **Streamed response buffering**: For cache misses, buffer the upstream SSE stream as it is forwarded to the client, then persist the assembled response to Redis on stream completion.
- **Synthetic SSE re-streaming**: On cache hits, replay the cached response as a sequence of SSE `data:` chunks to the client, indistinguishable from a live upstream response.
- **Cache-aware response headers**: Attach `X-Cache: HIT` / `X-Cache: MISS` headers so clients and telemetry can observe cache behavior.

## Capabilities

### New Capabilities
- `embedding-engine`: Local sentence embedding via `all-MiniLM-L6-v2` for vectorizing user messages.
- `cache-store`: Redis-backed vector store with RediSearch index for persisting and querying cached responses.
- `cache-lookup`: Semantic similarity search with composite key filtering and context hash verification.
- `response-buffering`: Transparent stream interception that buffers upstream SSE chunks for cache persistence.
- `cache-replay`: Synthetic SSE re-streaming of cached responses to the client on cache hit.

### Modified Capabilities
- `chat-proxy`: The chat completions route gains a cache-check-first flow — on hit, the upstream call is skipped entirely and the cached response is replayed.

## Impact

- **New dependencies**: `sentence-transformers`, `redis[hiredis]`, `numpy` added to `pyproject.toml`.
- **Infrastructure**: Requires a Redis 7+ instance with the RediSearch module (e.g., `redis/redis-stack` image running via OrbStack).
- **Configuration**: New settings — `redis_url`, `cache_ttl`, `cache_similarity_threshold`, `cache_enabled` toggle.
- **Affected code**: `src/routers/chat.py` (cache interception), `src/config.py` (new settings), `src/app.py` (embedding engine + Redis lifecycle). New package `src/cache/` for all caching logic.
- **Performance**: First request per unique query adds ~5ms embedding overhead. Cache hits eliminate upstream latency entirely (typically 1-10s → <50ms).
- **No breaking changes** to the existing OpenAI-compatible API surface.
