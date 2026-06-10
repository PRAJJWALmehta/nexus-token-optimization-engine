## ADDED Requirements

### Requirement: Pruning pipeline orchestration
The system SHALL provide a `PruningPipeline` that executes all pruning transforms in a defined order on a `ChatCompletionRequest` and returns a pruned copy with metadata about token savings.

#### Scenario: Full pipeline execution order
- **WHEN** the pipeline processes a request with all transforms enabled
- **THEN** it SHALL execute transforms in this order: whitespace normalization → comment stripping → system deduplication → conversation truncation

#### Scenario: Pipeline returns modified copy
- **WHEN** the pipeline processes a request
- **THEN** it SHALL return a new `ChatCompletionRequest` object, not mutate the original

#### Scenario: Pipeline returns pruning metadata
- **WHEN** the pipeline completes processing
- **THEN** it SHALL return a `PruningResult` containing: the pruned request, the estimated tokens before pruning, the estimated tokens after pruning, and a list of which transforms were applied

### Requirement: Individual transform toggles
The system SHALL allow each pruning transform to be independently enabled or disabled via environment variables.

#### Scenario: Whitespace normalization disabled
- **WHEN** `PRUNING_NORMALIZE_WHITESPACE` is set to `false`
- **THEN** the pipeline SHALL skip whitespace normalization but still execute other enabled transforms

#### Scenario: Comment stripping disabled
- **WHEN** `PRUNING_STRIP_COMMENTS` is set to `false`
- **THEN** the pipeline SHALL skip comment stripping but still execute other enabled transforms

#### Scenario: System deduplication disabled
- **WHEN** `PRUNING_DEDUPLICATE_SYSTEM` is set to `false`
- **THEN** the pipeline SHALL skip system deduplication but still execute other enabled transforms

#### Scenario: Conversation truncation disabled
- **WHEN** `PRUNING_TRUNCATE_CONVERSATION` is set to `false`
- **THEN** the pipeline SHALL skip conversation truncation but still execute other enabled transforms

#### Scenario: All transforms disabled
- **WHEN** all individual transform toggles are set to `false`
- **THEN** the pipeline SHALL return the original request unchanged with zero tokens saved

### Requirement: Global pruning toggle
The system SHALL provide a `PRUNING_ENABLED` environment variable that controls whether the entire pruning pipeline runs. When `false`, the pipeline is bypassed completely.

#### Scenario: Pruning globally disabled
- **WHEN** `PRUNING_ENABLED` is set to `false`
- **THEN** the pipeline SHALL NOT be invoked at all, and no pruning headers SHALL be set

#### Scenario: Pruning globally enabled (default)
- **WHEN** `PRUNING_ENABLED` is not set
- **THEN** the pipeline SHALL run with default settings (all transforms enabled)

### Requirement: Pruning observability headers
The system SHALL expose pruning metadata via HTTP response headers when pruning is applied.

#### Scenario: Tokens saved header
- **WHEN** the pruning pipeline reduces the estimated token count
- **THEN** the response SHALL include an `X-Tokens-Saved` header with the number of tokens saved (integer)

#### Scenario: Pruning applied header
- **WHEN** the pruning pipeline applies one or more transforms
- **THEN** the response SHALL include an `X-Pruning-Applied` header with a comma-separated list of transform names that were applied (e.g., `whitespace,comments,dedup,truncation`)

#### Scenario: No savings — headers still set
- **WHEN** the pruning pipeline runs but achieves zero token savings
- **THEN** the response SHALL include `X-Tokens-Saved: 0` and `X-Pruning-Applied` with the list of transforms that ran

### Requirement: Pruning pipeline logging
The system SHALL log pruning activity at INFO level including the tenant ID, transforms applied, tokens before, tokens after, and tokens saved.

#### Scenario: Pruning logged on completion
- **WHEN** the pipeline finishes processing a request for tenant `tenant-123`
- **THEN** the system SHALL log at INFO level with fields: tenant_id, transforms_applied, tokens_before, tokens_after, tokens_saved
