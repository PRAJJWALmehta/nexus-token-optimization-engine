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

### Configuration

| Env Var | Default | Description |
|---|---|---|
| `ROUTING_ENABLED` | `true` | Master toggle for dynamic routing |
| `ROUTING_TRIGGER_MODEL` | `auto` | Model name that activates routing |
| `ROUTING_TOKEN_THRESHOLD` | `2000` | Estimated token boundary for high complexity |
| `ROUTING_LOW_MODEL` | `claude-sonnet-4-20250514` | Target model for low-complexity requests |
| `ROUTING_HIGH_MODEL` | `claude-opus-4-0520` | Target model for high-complexity requests |
| `ROUTING_COMPLEXITY_KEYWORDS` | `refactor,architect,...` | Comma-separated keyword list |

### Response headers

| Header | When | Meaning |
|---|---|---|
| `X-Routed-Model` | Routed request, cache MISS/BYPASS | Model that processed the request |
| `X-Cached-Model` | Routed request, cache HIT | Model that originally generated the cached response |
| `X-Cache` | Always | `HIT` / `MISS` / `BYPASS` |

