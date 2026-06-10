## Context

The Nexus Token-Optimization Gateway currently proxies all chat completion requests to a single upstream model specified by the client. The gateway already implements semantic caching (Phase 2), which avoids redundant upstream calls. However, requests that *do* reach the upstream are all sent to whatever model the client specifies — there is no intelligence at the gateway layer to optimize which model handles a given request.

The upstream is an OpenAI-compatible endpoint (`UPSTREAM_API_URL`), which accepts a `model` field in the request payload. The gateway can therefore route to different models by simply overriding this field before forwarding.

The existing request flow is:
```
Client → TenantMiddleware → ChatRouter → CacheLookup → ProviderAdapter → Upstream
```

Dynamic routing will insert a classification + model resolution step before cache lookup:
```
Client → TenantMiddleware → ChatRouter → ModelRouter → CacheLookup → ProviderAdapter → Upstream
```

## Goals / Non-Goals

**Goals:**
- Reduce API costs by routing simple requests to cheaper models
- Make routing opt-in via a trigger model name (`auto`) so existing users are unaffected
- Keep the routing logic simple, deterministic, and fast (< 1ms overhead)
- Make all routing parameters configurable via environment variables
- Provide observability via response headers (`X-Routed-Model`)

**Non-Goals:**
- ML-based complexity classification (future iteration — Phase 3 is heuristic-only)
- Multi-provider routing (e.g., routing to OpenAI vs Anthropic endpoints); we only override the model field
- Per-tenant routing rules (all tenants share the same routing configuration)
- Quality feedback loops or A/B testing of routing decisions
- Token counting accuracy — approximate is sufficient for heuristic classification

## Decisions

### 1. Opt-in via trigger model name

**Decision**: Routing only activates when `model: "auto"` (configurable via `ROUTING_TRIGGER_MODEL`). All other model values pass through unchanged.

**Alternatives considered**:
- *Always-on with opt-out header*: Simpler config, but risks breaking existing integrations that depend on a specific model being used. Violates principle of least surprise.
- *Per-request header toggle*: More granular control, but requires clients to change their integration. A special model name works with any OpenAI-compatible client without modification.

**Rationale**: Opt-in is the safest default. Users explicitly choose routing by setting `model: "auto"`. This requires zero client-side changes beyond the model name.

### 2. Heuristic complexity classification (token count + keywords)

**Decision**: Classify requests into **low** or **high** complexity using two signals:
1. **Estimated token count**: Sum of all message content lengths ÷ 4 (char-to-token approximation). Threshold default: 2000 tokens.
2. **Keyword signals**: Scan the last user message for high-complexity keywords (e.g., "refactor", "architect", "design", "optimize", "analyze", "debug", "review", "explain in detail"). If any keyword matches, classify as high regardless of token count.

A request is **high** complexity if *either* signal triggers. Otherwise it's **low**.

**Alternatives considered**:
- *tiktoken for accurate counting*: Adds a dependency (~10MB) for marginal accuracy gain. The routing threshold is a rough heuristic anyway — precise token counting adds cost without proportional benefit.
- *Word count*: Less accurate than char/4 and provides no advantage. Char/4 is the industry standard approximation.
- *ML classifier*: Out of scope for Phase 3. The heuristic approach lets us ship quickly and iterate.

**Rationale**: The classification is intentionally simple. The cost of misrouting a single request is low (slightly higher cost or slightly lower quality), while the aggregate savings from correctly routing the majority of requests are significant.

### 3. Route before cache lookup

**Decision**: The model router resolves the final model name *before* the cache lookup step. The resolved model becomes part of the cache key naturally (since `model` is already a cache key component).

**Alternatives considered**:
- *Route after cache miss*: Would mean cache hits might serve a response from the wrong model. E.g., a Sonnet response cached when Opus should be used now. Incorrect.
- *Cache ignores model for routing*: Would require cache key changes and introduces semantic ambiguity.

**Rationale**: Route-before-cache is the only correct approach given that the cache key already includes `model`. It also means cache hits respect the routing decision.

### 4. Single upstream URL with model field override

**Decision**: Keep the existing single `UPSTREAM_API_URL`. The router only changes the `model` field in the request payload. No new provider instances or connection pools needed.

**Alternatives considered**:
- *Multiple upstream URLs*: Would require a provider registry and connection pool management. Overkill when the upstream is a single OpenAI-compatible API that supports multiple models.
- *Provider-per-model*: Over-engineered for the current use case.

**Rationale**: Model field override is the simplest approach and works with any OpenAI-compatible API (OpenAI, Anthropic via proxy, Azure OpenAI, etc.).

### 5. Module structure: `src/routing/`

**Decision**: Create a new `src/routing/` package with:
- `classifier.py` — `ComplexityClassifier` class with `classify(request) → ComplexityLevel` method
- `router.py` — `ModelRouter` class with `resolve(request) → request` method that mutates the model field if applicable
- `config.py` — Routing-specific settings (or extend `src/config.py`)

**Rationale**: Follows the existing package-per-concern pattern (`src/cache/`, `src/providers/`, `src/middleware/`). Keeping classifier and router separate allows testing each independently.

### 6. Token estimation: `len(text) / 4`

**Decision**: Use character count divided by 4 as the token estimate. Applied to the concatenation of all message `content` fields.

**Rationale**: This is the standard approximation used widely (OpenAI cookbook, LangChain, etc.). For routing purposes, ±20% accuracy is acceptable since the threshold itself is a heuristic. Adding `tiktoken` would introduce a heavy dependency for negligible benefit in this context.

## Risks / Trade-offs

- **Misrouting complex requests to cheaper model** → Mitigation: keyword signals catch most complex tasks even if they're short. The threshold is tunable. Users can always specify an explicit model to bypass routing.

- **Keyword list maintenance** → Mitigation: Keywords are configurable via `ROUTING_COMPLEXITY_KEYWORDS` env var. Can be updated without code changes.

- **Token estimation inaccuracy** → Mitigation: The threshold is a soft boundary, not a hard guarantee. ±20% error on a 2000-token threshold means routing changes at ~1600-2400 tokens, which is acceptable for cost optimization.

- **Cache fragmentation** → Routing before cache means the same prompt could be cached under different models if routing logic changes (e.g., threshold adjustment). This is correct behavior but may reduce cache hit rates during config changes. Mitigation: This is expected and acceptable.

- **No rollback mechanism per-request** → If routing sends a request to the wrong model, there's no retry with a different model. Mitigation: The cost of a single misrouted request is negligible. Aggregate correctness matters more.
