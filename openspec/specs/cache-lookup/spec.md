## ADDED Requirements

### Requirement: Composite cache key construction
The system SHALL construct a composite cache key from the incoming request consisting of: `tenant_id`, a SHA-256 hash of concatenated system-role messages, the `model` field, a bucketed temperature value (`round(temperature * 10)`), and a SHA-256 hash of the full message history excluding the last user message.

#### Scenario: Cache key built from standard request
- **WHEN** a chat completion request is received with tenant_id "acme", a system message, model "gpt-4o", temperature 0.7, and a multi-turn conversation
- **THEN** the system SHALL produce a cache key containing `tenant_id="acme"`, `sys_prompt_hash=SHA256(system messages)`, `model="gpt-4o"`, `temp_bucket=7`, and `ctx_hash=SHA256(all messages except last user message)`

#### Scenario: Request with no system message
- **WHEN** a chat completion request contains no system-role messages
- **THEN** the system SHALL use an empty-string hash for `sys_prompt_hash`

#### Scenario: Request with null temperature
- **WHEN** a chat completion request has `temperature` set to `null` or omitted
- **THEN** the system SHALL use a default temperature bucket of `10` (representing 1.0)

### Requirement: Semantic similarity search with metadata filtering
The system SHALL embed the last user message and perform a filtered ANN search against the RediSearch index, scoped by `tenant_id`, `sys_prompt_hash`, `model`, and `temp_bucket`, returning the top-1 result if its cosine similarity meets or exceeds the configured threshold.

#### Scenario: Semantically identical prompt found in cache
- **WHEN** a request's last user message embedding has cosine similarity ≥ 0.95 (default threshold) to a cached entry with matching metadata filters
- **AND** the cached entry's `ctx_hash` matches the request's computed `ctx_hash`
- **THEN** the system SHALL return the cached entry as a cache HIT

#### Scenario: Similar prompt but different conversation context
- **WHEN** a request's last user message embedding matches a cached entry above the similarity threshold
- **BUT** the cached entry's `ctx_hash` does NOT match the request's computed `ctx_hash`
- **THEN** the system SHALL treat the request as a cache MISS

#### Scenario: No similar prompt found
- **WHEN** no cached entry within the tenant's partition meets the similarity threshold
- **THEN** the system SHALL treat the request as a cache MISS

#### Scenario: Similar prompt but different tenant
- **WHEN** tenant "acme" sends a request identical to one cached by tenant "beta"
- **THEN** the system SHALL treat the request as a cache MISS because the RediSearch filter scopes results to the requesting tenant only
