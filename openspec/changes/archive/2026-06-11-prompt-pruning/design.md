## Context

The Nexus Token-Optimization Gateway currently proxies chat completion requests through a pipeline of: tenant extraction → dynamic routing → cache lookup → upstream provider. The gateway already reduces costs through semantic caching (avoiding duplicate upstream calls) and dynamic routing (selecting cost-appropriate models). However, the *content* of requests is forwarded verbatim — including wasted tokens from redundant whitespace, code comments in pasted snippets, duplicate system instructions, and stale conversation history.

These wasted tokens have a compounding cost: they inflate prompt token billing, reduce cache hit rates (superficially different prompts that are semantically identical), and consume context window budget that could be used for actual content.

The existing request flow is:
```
Client → TenantMiddleware → ChatRouter → ModelRouter → CacheLookup → ProviderAdapter → Upstream
```

Prompt pruning will insert a deterministic transform step between routing and cache:
```
Client → TenantMiddleware → ChatRouter → ModelRouter → PruningPipeline → CacheLookup → ProviderAdapter → Upstream
```

## Goals / Non-Goals

**Goals:**
- Reduce token consumption by 20%+ on typical prompts through deterministic transforms
- Keep pruning fast (< 1ms overhead per request) with zero external dependencies
- Improve cache hit rates by normalizing superficial content differences
- Make all pruning steps independently toggleable via environment variables
- Provide observability via response headers (`X-Tokens-Saved`, `X-Pruning-Applied`)

**Non-Goals:**
- ML-based summarization or semantic compression (contradicts "fast, deterministic" goal)
- Modifying response content (pruning is request-only)
- Per-tenant pruning configuration (all tenants share the same pruning settings)
- Perfect comment stripping accuracy for all languages (regex-based, covers common cases)
- Preserving exact whitespace fidelity in non-code-block content (normalized whitespace is acceptable)

## Decisions

### 1. Pipeline position: after routing, before cache

**Decision**: The pruning pipeline runs after model routing but before cache lookup. The cache key is computed on pruned content.

**Alternatives considered**:
- *Before routing*: The routing classifier would see pruned (smaller) token counts, which could change routing decisions. This couples pruning and routing in confusing ways — e.g., pruning could cause a request to switch from Opus to Sonnet.
- *After cache miss, before upstream*: Cache would store unpruned content, missing the normalization benefit for cache hit rates. Two prompts differing only in whitespace would be separate cache entries.

**Rationale**: After routing + before cache is the sweet spot. Routing sees the client's original intent (correct classification), while the cache benefits from normalized content (higher hit rates). The pruned content is also what the upstream sees, so token savings are real.

### 2. Transform ordering: normalize → strip comments → deduplicate → truncate

**Decision**: Transforms execute in a fixed order:
1. **Whitespace normalization** — first, to standardize the text for subsequent transforms
2. **Comment stripping** — operates on normalized text for cleaner regex matching
3. **System deduplication** — runs after normalization so whitespace-only differences are eliminated
4. **Conversation truncation** — last, because it needs accurate token counts after all other reductions

**Rationale**: Each transform benefits from the preceding one. Normalization makes comment detection more reliable. Deduplication benefits from normalized whitespace. Truncation runs last because it needs to know the final token count after all other savings.

### 3. Token estimation: character count / 4

**Decision**: Use `len(text) // 4` for all token estimation, consistent with the existing routing classifier.

**Alternatives considered**:
- *tiktoken*: Accurate but adds ~10MB dependency and ~1ms per estimation. Overkill for a heuristic budget check.
- *Word count / 0.75*: Less standard than char/4, no clear advantage.

**Rationale**: Consistency with the existing codebase. The routing classifier already uses char/4. The pruning budget threshold is approximate anyway — the goal is "does this conversation fit in ~N tokens", not exact counting.

### 4. Comment stripping: regex-based, common languages

**Decision**: Use regex patterns to strip comments from code blocks. Supported languages:
- Python/Shell/Ruby: `#` single-line comments
- JS/TS/Java/C/Go/Rust: `//` single-line and `/* */` multi-line comments
- HTML/XML: `<!-- -->` comments
- SQL: `--` single-line comments

Comments are only stripped from content detected as code blocks (fenced ``` blocks or indented blocks). Prose content is left untouched.

**Alternatives considered**:
- *tree-sitter*: AST-accurate but heavy dependency, requires per-language grammar files. Planned for Phase 6 anyway.
- *Strip all comments everywhere*: Dangerous — could mangle prose that happens to contain `#` or `//`.

**Rationale**: Code blocks are easily identifiable by markdown fencing. Regex patterns for comment syntax are well-known and handle 95%+ of cases. False positives (e.g., `#` inside a string literal) are acceptable since we're optimizing for token savings, not compiler correctness.

### 5. System deduplication: exact content match after normalization

**Decision**: After whitespace normalization, detect system messages with identical `content` and collapse them into a single occurrence (keeping the first). Messages with different `name` fields are treated as distinct even if content matches.

**Alternatives considered**:
- *Semantic similarity via embeddings*: Contradicts "no ML" goal. Also introduces latency.
- *Fuzzy string matching (difflib)*: Complex to tune, unclear benefit over exact-after-normalization.
- *Content hash comparison*: Functionally equivalent to exact match after normalization, but adds unnecessary hashing step.

**Rationale**: After whitespace normalization, most "near-duplicate" system messages become exact duplicates. This is the simplest approach that handles the common case (copy-paste of system prompts, frameworks that inject the same system prompt multiple times).

### 6. Conversation truncation: sliding window with anchors

**Decision**: When total estimated tokens exceed the budget:
1. **Always keep**: All system messages + the first user message (establishes context)
2. **Always keep**: The last user message + any trailing assistant messages (current turn)
3. **Trim from middle**: Remove the oldest non-anchored messages first until within budget
4. If still over budget after removing all trimmable messages, truncate the content of the longest remaining message from the end

**Alternatives considered**:
- *Simple tail truncation*: Loses the initial context-setting user message, which often contains critical instructions.
- *Summarize old messages via LLM*: Requires an upstream call, adds latency, costs tokens. Contradicts "no ML" goal.
- *Drop all but last N messages*: Too aggressive — N is hard to choose statically.

**Rationale**: Preserving system messages and the conversation boundaries (first user message, current turn) retains the most important context. The middle of long conversations is typically the least valuable — it's often iterative back-and-forth that the model doesn't need to see in full.

### 7. Module structure: `src/pruning/`

**Decision**: Create a new `src/pruning/` package:
- `normalizer.py` — `WhitespaceNormalizer` class
- `comments.py` — `CommentStripper` class
- `dedup.py` — `SystemDeduplicator` class
- `truncation.py` — `ConversationTruncator` class
- `pipeline.py` — `PruningPipeline` orchestrator class
- `__init__.py` — public API re-exports

Each transform follows a common interface: `transform(request: ChatCompletionRequest) → ChatCompletionRequest` (returns a deep copy via `model_copy(deep=True)`, does not mutate the input). This enables before/after comparison for token savings metrics.

**Rationale**: Follows the existing package-per-concern pattern (`src/cache/`, `src/routing/`). Separate modules allow independent testing and toggling.

### 8. Always-on with env var toggle

**Decision**: Pruning is enabled by default via `PRUNING_ENABLED=true`. Individual transforms can be independently toggled. No per-request opt-in mechanism.

**Rationale**: Unlike routing (which changes which model handles a request), pruning is a transparent optimization — it should never change the semantic meaning of a request. There's no reason for a client to want to send wasteful whitespace to the upstream. If pruning somehow causes issues, the operator can disable it or disable individual transforms via env vars.

## Risks / Trade-offs

- **Comment stripping removes intentional comments** → Mitigation: Only strips from detected code blocks, not prose. Togglable via `PRUNING_STRIP_COMMENTS=false`. In practice, comments in prompts are almost always context that the model doesn't need (e.g., `// TODO: fix this` in a pasted snippet).

- **Whitespace normalization breaks formatting-sensitive content** → Mitigation: Code blocks (fenced with ```) preserve internal formatting. Only normalizes whitespace *between* content blocks and in prose.

- **System dedup removes intentionally repeated instructions** → Mitigation: Messages with different `name` fields are kept distinct. Extremely rare to intentionally duplicate system messages with identical content.

- **Conversation truncation loses context** → Mitigation: Anchored messages (system, first user, current turn) are always preserved. Budget is configurable and defaults to a generous value. The truncation is a last resort — most requests won't trigger it.

- **Regex comment stripping is imperfect** → Mitigation: False positives (stripping non-comment text) and false negatives (missing exotic comment syntax) are both low-impact. The 20% reduction target doesn't depend on perfect comment stripping alone — whitespace normalization and deduplication provide the bulk of savings.

- **Cache key change on pruning toggle** → If pruning is toggled from enabled to disabled (or vice versa), cached responses from the previous state won't match. Mitigation: This is expected and acceptable — it's the same behavior as changing any other processing parameter.

### 9. Error handling: skip-on-error per transform

**Decision**: If a transform throws an unexpected exception, the pipeline catches the error, logs it at ERROR level, skips that transform, and continues with the next. The request is never blocked by a pruning failure.

**Rationale**: Pruning is a transparent optimization — it should never be the reason a request fails. A regex edge case in comment stripping shouldn't prevent the request from reaching the upstream.

### 10. Code block detection: fenced only

**Decision**: Only fenced code blocks (delimited by ``` or ~~~) are treated as code. Indented code blocks (4+ spaces) are not detected.

**Alternatives considered**:
- *Fenced + indented*: High false-positive risk — many prompts have indented lists, instructions, or hierarchical content that aren't code.
- *Heuristic code detection*: Fragile and language-dependent.

**Rationale**: Fenced blocks have unambiguous boundaries and cover 95%+ of code in LLM prompts. Indented block detection would require markdown parsing and risks mangling prose.

### 11. String literal awareness: simple same-line heuristic

**Decision**: When stripping comments, skip lines where the comment character (`#`, `//`, `--`) appears inside matched quotes on the same line. This handles `url = "https://..."` and `msg = "# heading"` but won't catch multi-line strings or escaped quotes.

**Rationale**: A full state-machine lexer per language is overkill. The simple heuristic handles 90%+ of real cases. False negatives (not stripping a real comment) are harmless — they just leave a few extra tokens.

### 12. Tool call/result atomic pairing during truncation

**Decision**: During conversation truncation, tool_call assistant messages and their corresponding tool-role responses are treated as atomic pairs. Removing one always removes the other.

**Rationale**: A tool response without its call (or vice versa) creates a structurally invalid conversation that would confuse the model.

### 13. Short-circuit optimization

**Decision**: Each transform checks a fast precondition before doing work:
- Dedup: skip if ≤ 1 system message
- Truncation: skip if total tokens < budget
- Comment stripping: skip if no fenced code blocks detected
- Whitespace normalization: always runs (cheapest and most impactful)

**Rationale**: Each check is O(1) or O(n) scan and avoids unnecessary deep copies on requests that wouldn't benefit.

### 14. Dependency injection: FastAPI Depends()

**Decision**: The `PruningPipeline` is injected via `Depends(get_pruning_pipeline)`, consistent with the `ModelRouter` pattern. The pipeline is stateless and instantiated from settings.

**Rationale**: Consistent with existing patterns. Enables test overrides via `app.dependency_overrides`.

### 15. Message role scope: all roles pruned

**Decision**: Whitespace normalization and comment stripping apply to all message roles (system, user, assistant, tool). Only system deduplication is restricted to system-role messages.

**Rationale**: Wasted tokens cost the same regardless of which role produced them. Assistant messages in long conversations often contain verbose formatting that benefits from normalization.

### 16. Prose normalization: aggressive outside code blocks

**Decision**: Whitespace normalization collapses all runs of spaces/tabs to single spaces in prose content. Only code blocks are preserved verbatim.

**Rationale**: Markdown headings (`#`) are not affected by whitespace normalization. Tables and ASCII art may lose alignment, but this is an acceptable trade-off for token savings. Operators can disable whitespace normalization via `PRUNING_NORMALIZE_WHITESPACE=false` if needed.
