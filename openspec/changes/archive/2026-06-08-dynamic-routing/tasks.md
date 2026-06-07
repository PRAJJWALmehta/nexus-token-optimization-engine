## 1. Configuration

- [x] 1.1 Add routing settings to `src/config.py` — new fields: `routing_enabled` (bool, default `True`), `routing_trigger_model` (str, default `"auto"`), `routing_token_threshold` (int, default `2000`), `routing_low_model` (str, default `"claude-sonnet-4-20250514"`), `routing_high_model` (str, default `"claude-opus-4-0520"`), `routing_complexity_keywords` (str, default comma-separated list of `refactor,architect,design,optimize,analyze,debug,review,explain`)

## 2. Complexity Classifier

- [x] 2.1 Create `src/routing/__init__.py` package
- [x] 2.2 Implement `src/routing/classifier.py` — `ComplexityLevel` enum (`LOW`, `HIGH`), `ComplexityClassifier` class with `classify(request: ChatCompletionRequest) → ComplexityResult`. Scoped to last user message + all system messages only (excludes assistant/tool messages). Estimates tokens via `sum(len(content)) // 4` over scoped messages. Uses whole-word keyword matching (case-insensitive). Handles multimodal content by extracting `text` parts from list-type content and ignoring `image_url` parts. Returns `LOW` by default when no user message is present.
- [x] 2.3 Unit tests for classifier — `tests/unit/test_classifier.py`

## 3. Model Router

- [x] 3.1 Implement `src/routing/router.py` — `ModelRouter` class with `resolve(request: ChatCompletionRequest) → RoutingResult`. Mutates `request.model` in place. Returns `RoutingResult(routed_model=resolved_name)` if routing applied, `RoutingResult(routed_model=None)` if bypassed. When `routing_enabled=False` and model matches trigger, raises `RoutingDisabledError` (400). Logs routing decisions at INFO level with structured fields (original model, resolved model, complexity, tokens_est, keyword_match).
- [x] 3.2 Unit tests for router — `tests/unit/test_router.py`

## 4. Chat Router Integration

- [x] 4.1 Modify `src/routers/chat.py` — add `ModelRouter` dependency injection, invoke `router.resolve(request_data)` before cache lookup, set `X-Routed-Model` header on cache MISS/BYPASS responses when routing applied, set `X-Cached-Model` header on cache HIT responses when routing applied
- [x] 4.2 Integration tests — `tests/integration/test_routing_integration.py`: test "Format this JSON" with `model: "auto"` routes to Sonnet, test "Refactor this architecture" with `model: "auto"` routes to Opus, test explicit model name bypasses routing, test `X-Routed-Model` header on cache MISS, test `X-Cached-Model` header on cache HIT, test routing disabled + `model: "auto"` → 400, test routing disabled + explicit model → passthrough

## 5. Documentation & Env Config

- [x] 5.1 Update `.env` with commented-out routing env vars as documentation
- [x] 5.2 Add routing section to `README.md`
