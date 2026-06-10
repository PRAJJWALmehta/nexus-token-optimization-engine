## MODIFIED Requirements

### Requirement: Semantic similarity search with metadata filtering
The system SHALL embed the last user message and perform a filtered ANN search against the RediSearch index, scoped by `tenant_id`, `sys_prompt_hash`, `model`, and `temp_bucket`, returning the top-1 result if its cosine similarity meets or exceeds the configured threshold. Upon completion of the search, the system SHALL record the outcome by incrementing `cache_hits_total` or `cache_misses_total` and, if a hit, record the savings in `tokens_saved_total`.

#### Scenario: Semantically identical prompt found in cache
- **WHEN** a request's last user message embedding has cosine similarity ≥ 0.95 (default threshold) to a cached entry with matching metadata filters
- **AND** the cached entry's `ctx_hash` matches the request's computed `ctx_hash`
- **THEN** the system SHALL return the cached entry as a cache HIT
- **AND** the system SHALL increment the `cache_hits_total` metric
- **AND** the system SHALL increment `tokens_saved_total` by the number of tokens saved by the hit

#### Scenario: Similar prompt but different conversation context
- **WHEN** a request's last user message embedding matches a cached entry above the similarity threshold
- **BUT** the cached entry's `ctx_hash` does NOT match the request's computed `ctx_hash`
- **THEN** the system SHALL treat the request as a cache MISS
- **AND** the system SHALL increment the `cache_misses_total` metric

#### Scenario: No similar prompt found
- **WHEN** no cached entry within the tenant's partition meets the similarity threshold
- **THEN** the system SHALL treat the request as a cache MISS
- **AND** the system SHALL increment the `cache_misses_total` metric

#### Scenario: Similar prompt but different tenant
- **WHEN** tenant "acme" sends a request identical to one cached by tenant "beta"
- **THEN** the system SHALL treat the request as a cache MISS because the RediSearch filter scopes results to the requesting tenant only
- **AND** the system SHALL increment the `cache_misses_total` metric
