## ADDED Requirements

### Requirement: Transparent stream interception for caching
The system SHALL wrap the upstream provider's SSE byte stream in a buffer that yields each chunk to the client in real-time while accumulating the complete response in memory for cache persistence.

#### Scenario: Streaming response buffered during pass-through
- **WHEN** a streaming cache-miss request is forwarded to the upstream provider
- **THEN** the system SHALL yield each SSE byte chunk to the client with no additional latency AND SHALL accumulate all chunks in an internal buffer

#### Scenario: Buffer persisted to cache on stream completion
- **WHEN** the upstream SSE stream completes (after `data: [DONE]` sentinel)
- **THEN** the system SHALL asynchronously persist the buffered response bytes, the request's embedding vector, and all cache metadata to Redis

#### Scenario: Upstream stream errors mid-response
- **WHEN** the upstream provider connection drops or errors during streaming
- **THEN** the system SHALL NOT persist the partial response to the cache and SHALL propagate the error to the client

### Requirement: Non-streaming response buffering
The system SHALL capture the complete JSON response body from non-streaming upstream responses and persist it to the cache.

#### Scenario: Non-streaming response cached
- **WHEN** a non-streaming cache-miss request receives a complete JSON response from the upstream provider
- **THEN** the system SHALL persist the response body and cache metadata to Redis asynchronously after returning the response to the client
