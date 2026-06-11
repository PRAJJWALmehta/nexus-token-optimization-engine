# Nexus Token-Optimization Gateway

A transparent, OpenAI-compatible reverse-proxy gateway that sits between LLM clients and upstream AI APIs. Layers in semantic caching, dynamic model routing, and (upcoming) prompt pruning to reduce cost without changing client code.

## Architecture

```
Client → POST /v1/chat/completions
       → [TenantMiddleware]
       → [ModelRouter]       ← Phase 3: Dynamic Routing
       → [CacheLookup]       ← Phase 2: Semantic Caching
       → [ProviderAdapter]
       → Upstream LLM API
```

## Getting Started

```bash
# Install dependencies
pip install -e .

# Configure upstream
export UPSTREAM_API_URL=https://api.openai.com/v1/chat/completions
export UPSTREAM_API_KEY=sk-...

# Run the gateway
python -m src
```

The gateway will start on `http://localhost:8000`. Point any OpenAI-compatible client at it.

## Dynamic Routing (Phase 3)

Send `model: "auto"` to let the gateway pick the right model for you based on request complexity.

```bash
# Simple task → routed to Sonnet (cheap)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Format this JSON: {}"}]}'
# Response header: X-Routed-Model: claude-sonnet-4-20250514

# Complex task → routed to Opus (capable)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", "messages": [{"role": "user", "content": "Refactor this architecture for microservices"}]}'
# Response header: X-Routed-Model: claude-opus-4-0520
```

### How routing works

1. **Token count**: estimates tokens via `len(all_content) // 4`. At or above threshold → high model.
2. **Keyword signals**: scans last user message + system messages for complexity keywords (whole-word). Any match → high model.
3. Explicit model names (anything other than `"auto"`) bypass routing entirely.

## Prompt Pruning (Phase 4)

The gateway automatically prunes chat completion requests to reduce token consumption and improve cache hit rates before they are forwarded upstream or checked against the semantic cache.

### Pruning pipeline transforms (in order):

1. **Whitespace Normalization**: Collapses consecutive spaces/tabs outside of code blocks to a single space, normalizes line endings to `\n`, strips trailing whitespace per line, and collapses three or more consecutive blank lines down to two.
2. **Comment Stripping**: Detects code fences and strips comments using regex rules matching the language (Python/Shell `#`, JS/TS/Java/C/Go/Rust `//` and `/* */`, HTML `<!-- -->`, SQL `--`, etc.).
3. **System Deduplication**: Deduplicates system messages with identical content (after whitespace-normalization), treating messages with different `name` fields as distinct.
4. **Conversation Truncation**: Truncates older non-anchored messages when the request exceeds a token budget (default `16,000` tokens, estimated as `characters // 4`). The system message, first user message, and final message turn are always preserved.

### Configuration

| Env Var | Default | Description |
|---|---|---|
| `ROUTING_ENABLED` | `true` | Master toggle for dynamic routing |
| `ROUTING_TRIGGER_MODEL` | `auto` | Model name that activates routing |
| `ROUTING_TOKEN_THRESHOLD` | `2000` | Estimated token boundary for high complexity |
| `ROUTING_LOW_MODEL` | `claude-sonnet-4-20250514` | Target model for low-complexity requests |
| `ROUTING_HIGH_MODEL` | `claude-opus-4-0520` | Target model for high-complexity requests |
| `ROUTING_COMPLEXITY_KEYWORDS` | `refactor,architect,...` | Comma-separated keyword list |
| `PRUNING_ENABLED` | `true` | Master toggle for prompt pruning |
| `PRUNING_TOKEN_BUDGET` | `16000` | Estimated token budget per request; 0 = unlimited |
| `PRUNING_NORMALIZE_WHITESPACE` | `true` | Enable whitespace normalization |
| `PRUNING_STRIP_COMMENTS` | `true` | Enable stripping comments from code blocks |
| `PRUNING_DEDUPLICATE_SYSTEM` | `true` | Enable collapsing duplicate system messages |
| `PRUNING_TRUNCATE_CONVERSATION` | `true` | Enable conversation history truncation |

### Response headers

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
