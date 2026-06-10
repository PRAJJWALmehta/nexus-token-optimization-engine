## ADDED Requirements

### Requirement: Token-budget-aware conversation truncation
The system SHALL enforce a configurable token budget on the total estimated token count of all messages in a `ChatCompletionRequest`. When the total exceeds the budget, the system SHALL remove messages to bring the total within budget.

#### Scenario: Under-budget request unchanged
- **WHEN** a request's total estimated token count is below the configured budget
- **THEN** the truncator SHALL return the request unchanged

#### Scenario: Over-budget request truncated
- **WHEN** a request's total estimated token count exceeds the configured budget
- **THEN** the truncator SHALL remove messages until the total is at or below the budget

#### Scenario: Token estimation method
- **WHEN** the truncator estimates token count for a message
- **THEN** it SHALL use `len(content) // 4` (character count divided by 4, rounded down) consistent with the existing routing classifier

### Requirement: Anchored message preservation
The system SHALL always preserve certain "anchored" messages during truncation, regardless of the token budget:
- All system messages
- The first user message in the conversation
- The last user message in the conversation
- Any assistant or tool messages following the last user message (current turn)

#### Scenario: System messages always preserved
- **WHEN** truncation is needed AND the request contains system messages
- **THEN** the truncator SHALL keep all system messages regardless of budget pressure

#### Scenario: First user message preserved
- **WHEN** truncation is needed AND the request contains multiple user messages
- **THEN** the truncator SHALL keep the first user message in its original position

#### Scenario: Current turn preserved
- **WHEN** truncation is needed AND the request ends with `[user-msg, assistant-msg]`
- **THEN** the truncator SHALL keep both the last user message and the trailing assistant message

#### Scenario: Only anchored messages remain
- **WHEN** all non-anchored messages are removed AND the total still exceeds the budget
- **THEN** the truncator SHALL keep the anchored messages as-is (never removes anchored messages)

### Requirement: Middle-out removal strategy
The system SHALL remove the oldest non-anchored messages first when truncating. Messages are removed one at a time from the oldest non-anchored position until the token budget is satisfied.

#### Scenario: Oldest non-anchored message removed first
- **WHEN** a conversation is `[system, user-1, assistant-1, user-2, assistant-2, user-3]` AND truncation is needed
- **THEN** the truncator SHALL first remove `assistant-1`, then `user-2`, then `assistant-2` (preserving system, user-1 as first user, and user-3 as last user)

#### Scenario: Message ordering preserved after truncation
- **WHEN** messages are removed from the middle of a conversation
- **THEN** the remaining messages SHALL maintain their original relative ordering

### Requirement: Configurable token budget
The system SHALL accept a configurable token budget via the `PRUNING_TOKEN_BUDGET` environment variable.

#### Scenario: Custom budget applied
- **WHEN** `PRUNING_TOKEN_BUDGET` is set to `4000`
- **THEN** the truncator SHALL use 4000 as the maximum estimated token count

#### Scenario: Default budget
- **WHEN** `PRUNING_TOKEN_BUDGET` is not set
- **THEN** the truncator SHALL use a default budget of `16000` tokens

#### Scenario: Budget of zero disables truncation
- **WHEN** `PRUNING_TOKEN_BUDGET` is set to `0`
- **THEN** the truncator SHALL skip truncation entirely (treat as unlimited)

### Requirement: Multimodal content token estimation
The system SHALL estimate tokens for multimodal content by summing the text content of all `text`-type parts and ignoring non-text parts for token counting purposes.

#### Scenario: Text parts counted
- **WHEN** a message has multimodal content with text parts totaling 400 characters
- **THEN** the truncator SHALL estimate 100 tokens for that message

#### Scenario: Image parts not counted
- **WHEN** a message has multimodal content with `image_url` parts
- **THEN** the truncator SHALL NOT include image parts in the token estimate
