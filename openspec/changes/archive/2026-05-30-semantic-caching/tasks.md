## 1. Project Setup & Dependencies

- [x] 1.1 Add `sentence-transformers`, `redis[hiredis]`, and `numpy` to `pyproject.toml` dependencies
- [x] 1.2 Add cache configuration fields to `src/config.py`: `redis_url`, `cache_ttl`, `cache_similarity_threshold`, `cache_enabled`, `cache_max_response_bytes`
- [x] 1.3 Create the `src/cache/` package directory with `__init__.py`

## 2. Embedding Engine

- [x] 2.1 Implement `src/cache/embedder.py` with `EmbeddingEngine` class that loads `all-MiniLM-L6-v2` at init and exposes an `encode(text: str) -> np.ndarray` method returning 384-dim vectors
- [x] 2.2 Handle edge cases: empty/whitespace input returns zero vector, model load failure logs error and sets a `disabled` flag
- [x] 2.3 Write tests for `EmbeddingEngine`: valid text encoding, empty input, vector dimensionality

## 3. Cache Key Builder

- [x] 3.1 Implement `src/cache/key_builder.py` with `CacheKeyBuilder` class that extracts `tenant_id`, `sys_prompt_hash`, `model`, `temp_bucket`, and `ctx_hash` from a `ChatCompletionRequest` and tenant ID
- [x] 3.2 Handle edge cases: no system message (empty hash), null/missing temperature (default bucket 10)
- [x] 3.3 Write tests for `CacheKeyBuilder`: standard request, no system prompt, null temperature, different tenants produce different keys

## 4. Redis Cache Store

- [x] 4.1 Implement `src/cache/store.py` with `RedisCacheStore` class that connects to Redis and creates the RediSearch HNSW vector index (`idx:cache`) on initialization
- [x] 4.2 Implement `store()` method to persist a cache entry (embedding vector, response bytes, metadata) as a Redis hash with TTL
- [x] 4.3 Implement `search()` method to perform filtered ANN query scoped by tenant_id, sys_prompt_hash, model, and temp_bucket, returning the top-1 result above the similarity threshold
- [x] 4.4 Add connection resilience: catch Redis connection errors in all methods, log warnings, return graceful defaults (None for search, no-op for store)
- [x] 4.5 Add max response size check — skip storing entries that exceed `cache_max_response_bytes`

## 5. Cache Lookup Orchestrator

- [x] 5.1 Implement `src/cache/lookup.py` with `CacheLookup` class that orchestrates the full cache check flow: build key → embed last user message → search Redis → verify ctx_hash → return HIT or MISS
- [x] 5.2 Return a `CacheResult` dataclass with `hit: bool`, `cached_response: Optional[bytes]`, and `cache_metadata` for header injection
- [x] 5.3 Handle graceful degradation: if embedding engine or Redis is unavailable, return MISS without error

## 6. Response Buffering

- [x] 6.1 Implement `src/cache/buffer.py` with `StreamBuffer` class that wraps an `AsyncIterator[bytes]`, yields chunks transparently, and accumulates them in an internal list
- [x] 6.2 Add `on_complete` callback that fires after the stream finishes — triggers async cache persistence via `asyncio.create_task`
- [x] 6.3 Handle stream errors: do NOT persist partial responses to cache on upstream errors

## 7. Cache Replay

- [x] 7.1 Implement `src/cache/replay.py` with `replay_sse_stream()` async generator that yields cached SSE bytes as chunks for streaming responses
- [x] 7.2 Implement `replay_json_response()` function that returns cached bytes as a `JSONResponse` for non-streaming responses

## 8. Chat Router Integration

- [x] 8.1 Modify `src/routers/chat.py` to inject `CacheLookup` dependency and perform cache check before forwarding to upstream
- [x] 8.2 On cache HIT (streaming): return `StreamingResponse` from `replay_sse_stream()` with `X-Cache: HIT` header
- [x] 8.3 On cache HIT (non-streaming): return `JSONResponse` from `replay_json_response()` with `X-Cache: HIT` header
- [x] 8.4 On cache MISS (streaming): wrap provider stream in `StreamBuffer`, return response with `X-Cache: MISS` header
- [x] 8.5 On cache MISS (non-streaming): buffer and cache the JSON response, return with `X-Cache: MISS` header
- [x] 8.6 When cache is disabled: pass through directly with `X-Cache: BYPASS` header

## 9. Application Lifecycle

- [x] 9.1 Modify `src/app.py` to initialize `EmbeddingEngine` and `RedisCacheStore` at startup (via FastAPI lifespan or startup event)
- [x] 9.2 Wire the initialized services into the `CacheLookup` dependency for the chat router
- [x] 9.3 Ensure graceful shutdown: close Redis connection pool on app shutdown

## 10. Integration Testing

- [x] 10.1 Write integration test: send a prompt, then send the same prompt again — verify second response has `X-Cache: HIT` header and near-zero latency
- [x] 10.2 Write integration test: send the same prompt from two different tenants — verify no cross-tenant cache hits
- [x] 10.3 Write integration test: verify `X-Cache: BYPASS` header when `cache_enabled=false`
- [x] 10.4 Write integration test: verify graceful degradation when Redis is unavailable (requests still succeed with `X-Cache: MISS`)
