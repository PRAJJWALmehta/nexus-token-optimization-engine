## Why

The gateway forwards every request to the upstream LLM with the exact content the client sent — including redundant whitespace, code comments in pasted snippets, duplicate system instructions, and stale conversation history that exceeds useful context. These are wasted tokens that inflate API costs without improving response quality. By applying deterministic, non-ML pruning transforms at the gateway layer, we can reduce token consumption by 20%+ on typical prompts with sub-millisecond overhead and zero quality loss.

## What Changes

- Introduce a **whitespace normalizer** that collapses runs of whitespace, normalizes line endings, and trims trailing whitespace from all message content — while preserving intentional formatting in code blocks.
- Add a **code comment stripper** that detects and removes single-line and multi-line comments from code blocks within message content. Supports Python (`#`), JS/TS/Java/C (`//`, `/* */`), HTML (`<!-- -->`), shell (`#`), and SQL (`--`).
- Implement **system instruction deduplication** that detects duplicate or near-duplicate system messages and collapses them into a single canonical message, preserving the first occurrence.
- Add **token-budget-aware conversation truncation** that trims older messages from long conversations to fit within a configurable token budget, using a sliding-window strategy that always preserves system messages, the first user message, and the most recent messages.
- Create a **pruning pipeline orchestrator** that chains all transforms in a defined order, tracks cumulative token savings, and exposes pruning metadata via response headers (`X-Tokens-Saved`, `X-Pruning-Applied`).
- All pruning is controlled by a single `PRUNING_ENABLED` env var (default: `True`) and runs transparently on all requests when enabled.

## Capabilities

### New Capabilities
- `whitespace-normalizer`: Collapses redundant whitespace in message content while preserving code block formatting.
- `comment-stripper`: Removes code comments from content blocks using regex-based detection for common languages.
- `system-deduplication`: Detects and collapses duplicate system messages within a request.
- `conversation-truncation`: Enforces a configurable token budget by trimming older messages using a sliding-window strategy.
- `pruning-pipeline`: Orchestrates all pruning transforms in sequence, tracks token savings, and exposes pruning metadata.

### Modified Capabilities
- `chat-proxy`: The chat completions endpoint must invoke the pruning pipeline after routing but before cache lookup, and include pruning metadata in response headers.

## Impact

- **Config** (`src/config.py`): New env vars — `PRUNING_ENABLED` (bool), `PRUNING_TOKEN_BUDGET` (int, max tokens per request), `PRUNING_STRIP_COMMENTS` (bool), `PRUNING_NORMALIZE_WHITESPACE` (bool), `PRUNING_DEDUPLICATE_SYSTEM` (bool), `PRUNING_TRUNCATE_CONVERSATION` (bool).
- **New module** (`src/pruning/`): Package containing `normalizer.py`, `comments.py`, `dedup.py`, `truncation.py`, `pipeline.py`.
- **Chat router** (`src/routers/chat.py`): Integration point — invoke pruning pipeline after routing, before cache check. Set `X-Tokens-Saved` and `X-Pruning-Applied` response headers.
- **Dependencies**: No new pip dependencies. All transforms use Python stdlib and regex.
- **Cache interaction**: Pruning runs before cache lookup, so the cache key is computed on pruned content. This means cache hits are more likely (pruned prompts normalize away superficial differences).
- **Tests**: Unit tests for each pruning module; integration test sending a bloated prompt and verifying 20%+ token reduction.
