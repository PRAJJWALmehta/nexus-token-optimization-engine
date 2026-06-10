## ADDED Requirements

### Requirement: Whitespace normalization in message content
The system SHALL normalize whitespace in all message `content` fields by collapsing consecutive whitespace characters (spaces, tabs) into single spaces, normalizing line endings to `\n`, and stripping trailing whitespace from each line.

#### Scenario: Consecutive spaces collapsed
- **WHEN** a message content contains `"Hello    world"`
- **THEN** the normalizer SHALL produce `"Hello world"`

#### Scenario: Mixed whitespace collapsed
- **WHEN** a message content contains tabs mixed with spaces (e.g., `"Hello\t\t  world"`)
- **THEN** the normalizer SHALL collapse them into a single space: `"Hello world"`

#### Scenario: Line ending normalization
- **WHEN** a message content contains `\r\n` or `\r` line endings
- **THEN** the normalizer SHALL convert them to `\n`

#### Scenario: Trailing whitespace stripped
- **WHEN** a line in message content ends with trailing spaces or tabs
- **THEN** the normalizer SHALL strip the trailing whitespace while preserving the line break

#### Scenario: Leading whitespace preserved
- **WHEN** a line in message content starts with leading spaces (e.g., indentation)
- **THEN** the normalizer SHALL preserve the leading whitespace

#### Scenario: Multiple blank lines collapsed
- **WHEN** message content contains three or more consecutive blank lines
- **THEN** the normalizer SHALL collapse them to a maximum of two consecutive blank lines

### Requirement: Code block preservation during normalization
The system SHALL preserve the internal formatting of fenced code blocks (delimited by ``` or ~~~) during whitespace normalization. Only content outside code blocks is normalized.

#### Scenario: Code block whitespace preserved
- **WHEN** a message contains a fenced code block with intentional indentation and multiple spaces
- **THEN** the normalizer SHALL NOT modify whitespace inside the code block

#### Scenario: Content outside code blocks normalized
- **WHEN** a message contains prose before and after a fenced code block with excessive whitespace
- **THEN** the normalizer SHALL normalize the prose whitespace while leaving the code block intact

### Requirement: Multimodal content handling
The system SHALL apply whitespace normalization to text content within multimodal message formats (list-of-parts content). Non-text parts (e.g., `image_url`) SHALL be passed through unchanged.

#### Scenario: Multimodal text parts normalized
- **WHEN** a message `content` is a list containing `{"type": "text", "text": "Hello    world"}`
- **THEN** the normalizer SHALL produce `{"type": "text", "text": "Hello world"}`

#### Scenario: Non-text parts preserved
- **WHEN** a message `content` is a list containing `{"type": "image_url", "image_url": {...}}`
- **THEN** the normalizer SHALL pass that part through unchanged
