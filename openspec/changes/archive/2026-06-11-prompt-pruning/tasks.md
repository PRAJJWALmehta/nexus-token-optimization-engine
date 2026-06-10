## 1. Configuration

- [x] 1.1 Add pruning settings to `src/config.py` — new fields: `pruning_enabled` (bool, default `True`), `pruning_token_budget` (int, default `16000`), `pruning_normalize_whitespace` (bool, default `True`), `pruning_strip_comments` (bool, default `True`), `pruning_deduplicate_system` (bool, default `True`), `pruning_truncate_conversation` (bool, default `True`)
- [x] 1.2 Update `.env` with commented-out pruning env vars as documentation

## 2. Whitespace Normalizer

- [x] 2.1 Create `src/pruning/__init__.py` package
- [x] 2.2 Implement `src/pruning/normalizer.py` — `WhitespaceNormalizer` class with `transform(request: ChatCompletionRequest) → ChatCompletionRequest`. Collapses consecutive spaces/tabs to single space, normalizes line endings to `\n`, strips trailing whitespace per line, collapses 3+ consecutive blank lines to 2. Preserves content inside fenced code blocks (``` or ~~~). Handles multimodal content (list-of-parts) by normalizing only `text`-type parts.
- [x] 2.3 Unit tests for normalizer — `tests/unit/test_normalizer.py`: test space collapsing, line ending normalization, trailing whitespace stripping, blank line collapsing, code block preservation, multimodal content handling, leading whitespace preservation

## 3. Code Comment Stripper

- [x] 3.1 Implement `src/pruning/comments.py` — `CommentStripper` class with `transform(request: ChatCompletionRequest) → ChatCompletionRequest`. Detects fenced code blocks and strips comments using language-appropriate regex. Supports Python/Shell (`#`), JS/TS/Java/C/Go/Rust (`//`, `/* */`), HTML (`<!-- -->`), SQL (`--`). Detects language from fence info string. Falls back to C-style patterns for unfenced blocks. Preserves comment-like syntax inside string literals. Cleans up blank lines from removed comment-only lines. Leaves prose content untouched.
- [x] 3.2 Unit tests for comment stripper — `tests/unit/test_comments.py`: test Python, JS, C-style multiline, HTML, SQL comment removal, fence language detection, string literal preservation, prose preservation, blank line cleanup after comment removal

## 4. System Instruction Deduplicator

- [x] 4.1 Implement `src/pruning/dedup.py` — `SystemDeduplicator` class with `transform(request: ChatCompletionRequest) → ChatCompletionRequest`. Detects system messages with identical content (after normalization) and collapses to first occurrence. Treats messages with different `name` fields as distinct. Preserves relative ordering of all messages. Does not deduplicate non-system messages.
- [x] 4.2 Unit tests for deduplicator — `tests/unit/test_dedup.py`: test exact duplicate removal, whitespace-only-difference dedup, different content preserved, multiple duplicates collapsed, different name fields preserved, named vs unnamed treated as distinct, message ordering preservation, non-system messages untouched

## 5. Conversation Truncation

- [x] 5.1 Implement `src/pruning/truncation.py` — `ConversationTruncator` class with `transform(request: ChatCompletionRequest) → ChatCompletionRequest`. Estimates tokens via `len(content) // 4`. Enforces configurable token budget (default 16,000). Always preserves anchored messages (system, first user, last user, current turn tail). Removes oldest non-anchored messages first. Treats tool_call + tool_result as atomic pairs (always remove both together). Short-circuits if total tokens < budget. Handles multimodal content for token estimation. Budget of 0 disables truncation.
- [x] 5.2 Unit tests for truncation — `tests/unit/test_truncation.py`: test under-budget unchanged, over-budget truncation, anchored message preservation (system, first user, last user, current turn), middle-out removal order, tool call/result atomic pairing, multimodal token estimation, budget=0 disables, message ordering after truncation

## 6. Pruning Pipeline Orchestrator

- [x] 6.1 Implement `src/pruning/pipeline.py` — `PruningPipeline` class that chains all transforms in order (normalize → comments → dedup → truncate). Returns `PruningResult` with pruned request (deep copy), tokens_before, tokens_after, transforms_applied list. Respects individual transform toggles. Wraps each transform in try/except — on error, logs at ERROR level, skips that transform, continues pipeline. Short-circuits transforms when preconditions aren't met (e.g., skip dedup if ≤1 system message). Logs pruning activity at INFO level.
- [x] 6.2 Update `src/pruning/__init__.py` with public API re-exports (`PruningPipeline`, `PruningResult`)
- [x] 6.3 Unit tests for pipeline — `tests/unit/test_pipeline.py`: test full pipeline execution order, individual toggles, all disabled returns original, PruningResult metadata correctness, token counting before/after, error in one transform doesn't block others, short-circuit skip logic

## 7. Chat Router Integration

- [x] 7.1 Modify `src/routers/chat.py` — add `PruningPipeline` via `Depends(get_pruning_pipeline)` (consistent with ModelRouter pattern), invoke pipeline after routing but before cache lookup, set `X-Tokens-Saved` and `X-Pruning-Applied` response headers on all response paths (cache HIT, MISS, BYPASS)
- [x] 7.2 Integration tests — `tests/integration/test_pruning_integration.py`: test realistic synthetic bloated prompt with all 4 waste patterns (3x duplicate system, ~40 lines code with 50% comments, excessive whitespace, 30-message conversation) → verify 20%+ token reduction, test pruning headers present on response, test pruning disabled → no headers + request unchanged, test individual toggles respected in end-to-end flow

## 8. Documentation

- [x] 8.1 Add pruning section to `README.md`
