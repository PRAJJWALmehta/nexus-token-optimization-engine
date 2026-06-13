## ADDED Requirements

### Requirement: Duplicate system message detection
The system SHALL detect system messages within a `ChatCompletionRequest` that have identical `content` after whitespace normalization and collapse them into a single occurrence.

#### Scenario: Exact duplicate system messages collapsed
- **WHEN** a request contains two system messages with identical `content` text
- **THEN** the deduplicator SHALL keep only the first occurrence and remove the duplicate

#### Scenario: Whitespace-only difference treated as duplicate
- **WHEN** a request contains two system messages whose `content` differs only in whitespace (e.g., trailing spaces, extra blank lines)
- **THEN** the deduplicator SHALL treat them as duplicates and keep only the first

#### Scenario: Different content preserved
- **WHEN** a request contains two system messages with different `content`
- **THEN** the deduplicator SHALL keep both messages

#### Scenario: Multiple duplicates collapsed
- **WHEN** a request contains five system messages with the same `content`
- **THEN** the deduplicator SHALL keep only one (the first) and remove the other four

### Requirement: System message identity by name field
The system SHALL treat system messages with different `name` fields as distinct, even if their `content` is identical.

#### Scenario: Same content but different names preserved
- **WHEN** a request contains system message A with `name: "rules"` and system message B with `name: "constraints"`, both with the same `content`
- **THEN** the deduplicator SHALL keep both messages

#### Scenario: Same content and same name deduplicated
- **WHEN** a request contains two system messages both with `name: "rules"` and identical `content`
- **THEN** the deduplicator SHALL keep only the first occurrence

#### Scenario: Named and unnamed treated as distinct
- **WHEN** a request contains system message A with no `name` field and system message B with `name: "default"`, both with the same `content`
- **THEN** the deduplicator SHALL keep both messages

### Requirement: Message ordering preservation
The system SHALL preserve the relative ordering of all messages in the request. When a duplicate system message is removed, the positions of remaining messages SHALL NOT change relative to each other.

#### Scenario: Non-system messages unaffected
- **WHEN** a request contains `[system-A, user-1, system-A-dup, assistant-1, user-2]`
- **THEN** the deduplicator SHALL produce `[system-A, user-1, assistant-1, user-2]`

### Requirement: Non-system messages excluded from deduplication
The system SHALL NOT deduplicate user, assistant, tool, or function messages, even if they have identical content.

#### Scenario: Duplicate user messages preserved
- **WHEN** a request contains two user messages with identical content
- **THEN** the deduplicator SHALL keep both user messages
