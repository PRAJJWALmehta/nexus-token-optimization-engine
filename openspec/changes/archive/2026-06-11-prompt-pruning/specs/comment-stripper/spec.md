## ADDED Requirements

### Requirement: Code comment removal from fenced code blocks
The system SHALL detect fenced code blocks (delimited by ``` or ~~~) within message content and remove code comments from them using language-appropriate regex patterns.

#### Scenario: Python single-line comment removal
- **WHEN** a fenced code block contains `x = 1  # set x to one`
- **THEN** the stripper SHALL produce `x = 1`

#### Scenario: JavaScript single-line comment removal
- **WHEN** a fenced code block contains `const x = 1; // set x to one`
- **THEN** the stripper SHALL produce `const x = 1;`

#### Scenario: C-style multi-line comment removal
- **WHEN** a fenced code block contains `/* this is\na multi-line\ncomment */`
- **THEN** the stripper SHALL remove the entire comment block

#### Scenario: HTML comment removal
- **WHEN** a fenced code block contains `<!-- this is a comment -->`
- **THEN** the stripper SHALL remove the comment

#### Scenario: SQL single-line comment removal
- **WHEN** a fenced code block contains `SELECT * FROM users -- get all users`
- **THEN** the stripper SHALL produce `SELECT * FROM users`

#### Scenario: Shell comment removal
- **WHEN** a fenced code block contains `echo "hello"  # print greeting`
- **THEN** the stripper SHALL produce `echo "hello"`

### Requirement: Language detection from fence info string
The system SHALL detect the programming language from the fenced code block's info string (e.g., ````python`, ````javascript`) to select appropriate comment patterns.

#### Scenario: Python fence detected
- **WHEN** a code block is fenced with ````python` or ````py`
- **THEN** the stripper SHALL use Python comment patterns (`#` for single-line)

#### Scenario: JavaScript fence detected
- **WHEN** a code block is fenced with ````javascript`, ````js`, ````typescript`, or ````ts`
- **THEN** the stripper SHALL use C-style comment patterns (`//` single-line, `/* */` multi-line)

#### Scenario: No fence info string
- **WHEN** a code block has no info string (bare ```)
- **THEN** the stripper SHALL apply a conservative set of comment patterns (C-style `//` and `/* */` only, to minimize false positives)

### Requirement: Comment preservation inside string literals
The system SHALL NOT strip comment-like syntax that appears inside string literals within code blocks.

#### Scenario: Hash inside Python string preserved
- **WHEN** a code block contains `url = "https://example.com/#section"`
- **THEN** the stripper SHALL NOT remove `#section` from the URL string

#### Scenario: Double-slash inside string preserved
- **WHEN** a code block contains `protocol = "https://example.com"`
- **THEN** the stripper SHALL NOT remove `//example.com`

### Requirement: Prose content untouched
The system SHALL NOT modify any content outside of fenced code blocks. Prose text containing comment-like characters (e.g., `#` in markdown headings, `//` in URLs) SHALL be preserved.

#### Scenario: Markdown heading preserved
- **WHEN** message content contains `# My Heading` outside a code block
- **THEN** the stripper SHALL NOT modify the heading

#### Scenario: URL in prose preserved
- **WHEN** message content contains `Visit https://example.com for details` outside a code block
- **THEN** the stripper SHALL NOT modify the URL

### Requirement: Empty line cleanup after comment removal
The system SHALL remove blank lines that result from comment-only lines being stripped, collapsing them so the code block doesn't have excessive empty lines.

#### Scenario: Comment-only line removed
- **WHEN** a code block contains a line that is only a comment (e.g., `# This function does X`)
- **THEN** the stripper SHALL remove the entire line, not leave a blank line in its place

#### Scenario: Consecutive comment-only lines removed
- **WHEN** a code block contains multiple consecutive comment-only lines
- **THEN** the stripper SHALL remove all of them without leaving multiple blank lines
