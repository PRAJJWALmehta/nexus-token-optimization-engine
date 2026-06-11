# Nexus Token-Optimization Gateway

A transparent, OpenAI-compatible reverse-proxy gateway that sits between LLM clients and upstream AI APIs. Layers in semantic caching, dynamic model routing, and prompt pruning to reduce cost without changing client code.

## Architecture

The request/response lifecycle follows this sequence of operations:

```
                               Request Lifecycle
                               
     Client
       │  POST /v1/chat/completions
       ▼
[TenantMiddleware]             (Extracts tenant identifier from API key)
       │
       ▼
[ModelRouter] (Phase 3)        (Optional: Resolves model from "auto")
       │
       ▼
[PruningPipeline] (Phase 4)    (Optional: Whitespace, comments, dedup, truncation)
       │
       ▼
[CacheLookup] (Phase 2)        (Checks semantic cache for matching prompts)
       ├───────────────── HIT ────────────────► [CacheReplay]
       │                                             │
      MISS / BYPASS                                  │ (Replay cached response)
       ▼                                             ▼
[ProviderAdapter]                                  Client
       │
       ▼ (Forward request to OpenAI / Upstream API)
  Upstream LLM
       │
       ▼ (Buffer & Persist response back to cache)
 [StreamBuffer] 
       │
       └──────────────────────────────────────► Client
```

## Getting Started

```bash
# Install dependencies
pip install -e .

# Configure upstream and gateway settings (or use a .env file)
export UPSTREAM_API_URL=https://api.openai.com/v1/chat/completions
export UPSTREAM_API_KEY=sk-...
export REDIS_URL=redis://localhost:6379

# Run the gateway
python -m src
```

The gateway will start on `http://localhost:8000`. Point any OpenAI-compatible client at it.

---

## Tenant Extraction & Multi-Tenancy

The gateway automatically resolves the tenant ID from the `Authorization: Bearer <key>` header using the prefix before the first `_` delimiter:
- `Authorization: Bearer tenantABC_sk-12345` ──► Tenant ID = `tenantABC`
- `Authorization: Bearer sk-no-prefix` ──► Tenant ID = `default`
- *(No authorization header)* ──► Tenant ID = `default`

Downstream services, including semantic caching, use this tenant ID to isolate cache entries and data scopes per tenant.

---

## Dynamic Routing (Phase 3)

Send `model: "auto"` to let the gateway pick the right model for you based on request complexity.

```bash
# Simple task → routed to low-cost model (claude-sonnet-4-20250514)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tenantXYZ_sk-mock-key" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Format this JSON: {}"}]}'
# Response header: X-Routed-Model: claude-sonnet-4-20250514

# Complex task → routed to capable model (claude-opus-4-0520)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tenantXYZ_sk-mock-key" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Refactor this architecture for microservices"}]}'
# Response header: X-Routed-Model: claude-opus-4-0520
```

### How routing works

1. **Token count**: estimates tokens via `len(relevant_messages_content) // 4` (only system messages and the last user message are analyzed). If it meets or exceeds `ROUTING_TOKEN_THRESHOLD` → high model.
2. **Keyword signals**: scans system messages and the last user message for complexity keywords (whole-word, case-insensitive). Any match → high model.
3. Explicit model names (anything other than `"auto"`) bypass routing entirely.

---

## Prompt Pruning (Phase 4)

The gateway automatically prunes chat completion requests to reduce token consumption and improve cache hit rates before they are forwarded upstream or checked against the semantic cache.

### Pruning pipeline transforms (in order):

1. **Whitespace Normalization**: Collapses consecutive spaces/tabs outside of code blocks to a single space, normalizes line endings to `\n`, strips trailing whitespace per line, and collapses three or more consecutive blank lines down to two.
2. **Comment Stripping**: Detects code fences and strips comments using regex rules matching the language (Python/Shell `#`, JS/TS/Java/C/Go/Rust `//` and `/* */`, HTML `<!-- -->`, SQL `--`, etc.).
3. **System Deduplication**: Deduplicates system messages with identical content (after whitespace-normalization), treating messages with different `name` fields as distinct.
4. **Conversation Truncation**: Truncates older non-anchored messages when the request exceeds a token budget (default `16,000` tokens, estimated as `characters // 4`). The system message, first user message, and final message turn are always preserved.

---

## Configuration

The gateway is configured via environment variables or a `.env` file:

| Env Var | Default | Description |
|---|---|---|
| **Upstream API Settings** | | |
| `UPSTREAM_API_URL` | `https://api.openai.com/v1/chat/completions` | Upstream OpenAI-compatible chat completions endpoint URL |
| `UPSTREAM_API_KEY` | `""` | Authorization key for upstream LLM provider |
| `UPSTREAM_TIMEOUT` | `120.0` | Timeout in seconds for upstream requests |
| **Server Settings** | | |
| `HOST` | `0.0.0.0` | Listen host for the gateway |
| `PORT` | `8000` | Listen port for the gateway |
| **Semantic Caching Settings** | | |
| `CACHE_ENABLED` | `true` | Master toggle for semantic caching |
| `REDIS_URL` | `redis://localhost:6379` | Redis server connection URL (supports Redis Stack) |
| `CACHE_TTL` | `3600` | Expiration time (in seconds) for cached responses |
| `CACHE_SIMILARITY_THRESHOLD` | `0.95` | Cosine similarity threshold for semantic cache hits |
| `CACHE_MAX_RESPONSE_BYTES` | `524288` | Maximum size in bytes of responses allowed to be cached (default: 512 KB) |
| **Dynamic Routing Settings** | | |
| `ROUTING_ENABLED` | `true` | Master toggle for dynamic routing |
| `ROUTING_TRIGGER_MODEL` | `auto` | Model name that activates routing |
| `ROUTING_TOKEN_THRESHOLD` | `2000` | Estimated token boundary for high complexity |
| `ROUTING_LOW_MODEL` | `claude-sonnet-4-20250514` | Target model for low-complexity requests |
| `ROUTING_HIGH_MODEL` | `claude-opus-4-0520` | Target model for high-complexity requests |
| `ROUTING_COMPLEXITY_KEYWORDS` | `refactor,architect,design,optimize,analyze,debug,review,explain` | Comma-separated keyword list |
| **Prompt Pruning Settings** | | |
| `PRUNING_ENABLED` | `true` | Master toggle for prompt pruning |
| `PRUNING_TOKEN_BUDGET` | `16000` | Estimated token budget per request; 0 = unlimited |
| `PRUNING_NORMALIZE_WHITESPACE` | `true` | Enable whitespace normalization |
| `PRUNING_STRIP_COMMENTS` | `true` | Enable stripping comments from code blocks |
| `PRUNING_DEDUPLICATE_SYSTEM` | `true` | Collapse duplicate system messages |
| `PRUNING_TRUNCATE_CONVERSATION` | `true` | Enable conversation history truncation |

---

## Response Headers

The gateway appends custom tracking headers to upstream responses:

| Header | When | Meaning |
|---|---|---|
| `X-Routed-Model` | Routed request, cache MISS/BYPASS | Model that processed the request |
| `X-Cached-Model` | Routed request, cache HIT | Model that originally generated the cached response |
| `X-Cache` | Always | `HIT` / `MISS` / `BYPASS` |
| `X-Tokens-Saved` | Pruning enabled | Number of estimated tokens saved by pruning |
| `X-Pruning-Applied` | Pruning enabled | Comma-separated list of applied pruning transforms (e.g. `whitespace,comments,dedup,truncation`) |


## Deterministic AST Extraction (Phase 5/6)

The gateway parses Python and TypeScript files to extract functions, classes, and dependencies/imports using Tree-sitter. This builds a local dependency graph in Graphify format, which can be queried for code dependency trees.

### AST Query API

* **Endpoint**: `GET /api/ast/query`
* **Query Parameters**:
  * `node_id` (required): The starting node ID to query dependencies for (e.g., function, class, or file identifier).
  * `depth` (optional, default: `2`, max: `10`): Max recursion depth to traverse outgoing dependencies.
* **Response**: Returns a JSON object with `"nodes"` and `"links"` forming a subgraph of dependencies.

### Local Graph Generation

To verify AST parsing and generate/update the local knowledge graph:
```bash
python -m scratch.verify_ast
```

---

## Telemetry & Observability (Phase 5)

Nexus exports real-time metrics using Prometheus and includes a pre-configured Grafana dashboard for full system visibility (latency, cache statistics, token savings, routing breakdown, and AST query performance).

### Running the Observability Stack

Start Redis Stack, Prometheus, and Grafana via Docker Compose:
```bash
docker-compose up -d
```

* **Prometheus URL**: `http://localhost:9090`
* **Grafana URL**: `http://localhost:3000` (default login: `admin` / `admin`)
* **Gateway Metrics Endpoint**: `http://localhost:8000/metrics`

---

## Performance Benchmark Suite

A performance load-testing suite designed to validate the caching mechanisms, latency (TTFT), and throughput under realistic or adversarial traffic.

### 1. Data Collection (Offline Process)
To ensure reliable, deterministic, and rapid benchmark runs without relying on live web requests, scrape the web once offline to create a rich static dataset of requests (`scratch/dummy_requests.jsonl`):
```bash
python -m scratch.data_collector
```

### 2. Running Benchmarks
Run the load testing script against the running gateway:
```bash
python -m scratch.benchmark_runner [options]
```

#### CLI Options:
* `--url`: Gateway endpoint URL (default: `http://localhost:8000/v1/chat/completions`).
* `--dataset`: Path to the compiled jsonl dataset (default: `scratch/dummy_requests.jsonl`).
* `--requests`: Total number of requests to dispatch (default: `30`).
* `--concurrency`: Number of concurrent requests (default: `5`).
* `--entropy`: Level of cache-busting entropy to inject (`none` or `high`, default: `none`). Set to `high` to inject unique nonces to guarantee a `<5%` cache hit rate.
* `--model`: Model name to request (default: `gpt-4o`, set to `auto` to test dynamic routing).
* `--stream`: Send requests in streaming mode (reports Time To First Token metrics).

---

## Running Tests

To run the unit, integration, and E2E test suites:
```bash
# Run all tests
pytest

# Run a specific test suite
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```
