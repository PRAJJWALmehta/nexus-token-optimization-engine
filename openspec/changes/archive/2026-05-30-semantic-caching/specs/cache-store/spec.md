## ADDED Requirements

### Requirement: Redis vector index schema
The system SHALL create a RediSearch vector index on application startup that supports HNSW-based approximate nearest neighbor search over 384-dimensional float vectors, with filterable metadata fields for `tenant_id`, `sys_prompt_hash`, `model`, and `temp_bucket`.

#### Scenario: Index created on first startup
- **WHEN** the application starts and the RediSearch index does not exist
- **THEN** the system SHALL create an index named `idx:cache` with a VECTOR field (HNSW, 384 dims, COSINE distance) and TAG fields for `tenant_id`, `sys_prompt_hash`, `model`, and `temp_bucket`

#### Scenario: Index already exists on startup
- **WHEN** the application starts and the RediSearch index already exists
- **THEN** the system SHALL reuse the existing index without error

### Requirement: Cache entry persistence
The system SHALL store cached responses as Redis hash entries with fields for the embedding vector, response bytes, metadata (tenant_id, sys_prompt_hash, model, temp_bucket, ctx_hash), and a TTL.

#### Scenario: Cache entry stored after upstream response completes
- **WHEN** an upstream response stream completes successfully for a cache-miss request
- **THEN** the system SHALL persist a Redis hash at key `cache:{uuid}` containing the embedding vector, serialized response bytes, and all metadata fields, with a TTL equal to the configured `cache_ttl` value

#### Scenario: Cache entry expires after TTL
- **WHEN** a cache entry's TTL elapses
- **THEN** Redis SHALL automatically remove the entry and it SHALL no longer appear in search results

#### Scenario: Response exceeds maximum cache size
- **WHEN** a buffered response exceeds the configured maximum cache entry size
- **THEN** the system SHALL discard the response without storing it in the cache and SHALL log a warning

### Requirement: Redis connection resilience
The system SHALL handle Redis connection failures gracefully without impacting request processing.

#### Scenario: Redis unavailable at startup
- **WHEN** the application starts and cannot connect to Redis
- **THEN** the system SHALL log a warning, disable caching, and operate in pass-through mode

#### Scenario: Redis becomes unavailable during operation
- **WHEN** a cache lookup or store operation fails due to a Redis connection error
- **THEN** the system SHALL log the error, skip the cache operation, and continue processing the request normally (pass-through to upstream)
