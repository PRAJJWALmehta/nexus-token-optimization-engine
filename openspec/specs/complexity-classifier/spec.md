## ADDED Requirements

### Requirement: Heuristic complexity classification
The system SHALL provide a complexity classifier that analyzes a `ChatCompletionRequest` and produces a complexity level of either `low` or `high` based on heuristic signals. The classifier SHALL analyze only the last user message and all system messages for both token estimation and keyword detection.

#### Scenario: Low complexity classification by token count
- **WHEN** a request is classified AND the estimated token count of the last user message and system messages is below the configured threshold (default: 2000) AND no high-complexity keywords are detected
- **THEN** the classifier SHALL return a complexity level of `low`

#### Scenario: High complexity classification by token count
- **WHEN** a request is classified AND the estimated token count of the last user message and system messages is at or above the configured threshold (default: 2000)
- **THEN** the classifier SHALL return a complexity level of `high`, regardless of keyword presence

#### Scenario: High complexity classification by keyword signal
- **WHEN** a request is classified AND the last user message or any system message contains any of the configured high-complexity keywords (case-insensitive, whole-word matching)
- **THEN** the classifier SHALL return a complexity level of `high`, regardless of token count

#### Scenario: Whole-word keyword matching
- **WHEN** the classifier scans for the keyword `"refactor"`
- **THEN** it SHALL match `"Please refactor this class"` but SHALL NOT match `"refactoring"` or `"refactored"`

#### Scenario: Token estimation method
- **WHEN** the classifier estimates the token count of message content
- **THEN** it SHALL use the total character count of the last user message and all system message `content` fields divided by 4 (rounded down) as the token estimate

#### Scenario: Empty or missing content handling
- **WHEN** a message has `null` or empty `content`
- **THEN** the classifier SHALL treat that message as contributing zero tokens and no keyword matches

#### Scenario: No user message present
- **WHEN** a request contains no user messages (only system and/or assistant messages)
- **THEN** the classifier SHALL default to a complexity level of `low`, unless system message keywords or token count triggers high complexity

#### Scenario: Multimodal content handling
- **WHEN** a message `content` field is a list of content parts (e.g., `[{"type": "text", "text": "..."}, {"type": "image_url", ...}]`)
- **THEN** the classifier SHALL extract and concatenate only the `text` fields from content parts with `type: "text"`, ignoring non-text parts like `image_url`

#### Scenario: Message scope exclusion
- **WHEN** a request contains assistant or tool messages
- **THEN** the classifier SHALL NOT include those messages in token estimation or keyword scanning

### Requirement: Configurable complexity keywords
The system SHALL allow the set of high-complexity keywords to be configured via the `ROUTING_COMPLEXITY_KEYWORDS` environment variable as a comma-separated list.

#### Scenario: Custom keyword configuration
- **WHEN** `ROUTING_COMPLEXITY_KEYWORDS` is set to `"refactor,architect,optimize"`
- **THEN** the classifier SHALL use exactly those keywords for detection, replacing the default set

#### Scenario: Default keyword set
- **WHEN** `ROUTING_COMPLEXITY_KEYWORDS` is not set
- **THEN** the classifier SHALL use a built-in default set of keywords including at minimum: `refactor`, `architect`, `design`, `optimize`, `analyze`, `debug`, `review`, `explain`

### Requirement: Configurable token threshold
The system SHALL allow the token complexity threshold to be configured via the `ROUTING_TOKEN_THRESHOLD` environment variable.

#### Scenario: Custom threshold
- **WHEN** `ROUTING_TOKEN_THRESHOLD` is set to `3000`
- **THEN** the classifier SHALL use 3000 as the boundary between low and high complexity for the token count signal

#### Scenario: Default threshold
- **WHEN** `ROUTING_TOKEN_THRESHOLD` is not set
- **THEN** the classifier SHALL use 2000 as the default token threshold
