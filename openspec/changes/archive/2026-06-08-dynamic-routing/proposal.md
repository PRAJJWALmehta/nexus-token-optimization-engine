## Why

The gateway currently forwards every request to a single upstream model, regardless of task complexity. Simple tasks like "format this JSON" consume the same expensive model as complex tasks like "refactor this architecture." By classifying request complexity at the gateway layer and routing to cost-appropriate models, we can significantly reduce API costs without degrading quality for tasks that genuinely need a more capable model. This is an opt-in feature triggered by a special model name (`auto`), so existing users are unaffected.

## What Changes

- Introduce a **heuristic complexity classifier** that analyzes incoming requests using estimated token count and keyword signals to produce a complexity score (low/high).
- Add **model routing logic** that maps complexity scores to specific upstream model names: low-complexity requests route to a cheaper model (default: Sonnet), high-complexity requests route to a more capable model (default: Opus).
- The **routing threshold** is configurable: requests below a token threshold (default: 2000) with no complexity keywords route to the cheaper model.
- Routing is **opt-in**: only requests with `model: "auto"` (or a configurable trigger name) are classified and rerouted. All other requests pass through with their original model unchanged.
- Routing happens **before cache lookup**, so the resolved model becomes part of the cache key — ensuring cache correctness across routed models.
- All routing configuration (trigger model name, threshold, model mappings, keyword lists) is exposed via **environment variables**.
- The routed model name is surfaced to the client via an `X-Routed-Model` response header for observability.

## Capabilities

### New Capabilities
- `complexity-classifier`: Heuristic engine that analyzes chat completion requests and produces a complexity classification (low/high) based on estimated token count and keyword signals.
- `model-router`: Request interceptor that resolves `model: "auto"` to a concrete model name based on complexity classification and configurable routing rules.

### Modified Capabilities
- `chat-proxy`: The chat completions endpoint must invoke the model router before cache lookup when the request model matches the routing trigger, and include routing metadata in response headers.

## Impact

- **Config** (`src/config.py`): New env vars for routing — trigger model name, token threshold, model mappings, complexity keywords.
- **New module** (`src/routing/`): Complexity classifier and model router logic.
- **Chat router** (`src/routers/chat.py`): Integration point — invoke router before cache check, set `X-Routed-Model` header.
- **Dependencies**: No new pip dependencies required. Token estimation uses character-based approximation (`len / 4`).
- **Cache interaction**: Routed model is resolved before cache lookup, so the cache key naturally includes the correct model. No changes to cache key builder needed.
- **Tests**: Unit tests for classifier and router; integration test verifying end-to-end routing through the chat endpoint.
