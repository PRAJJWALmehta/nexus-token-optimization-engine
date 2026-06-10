## ADDED Requirements

### Requirement: Synthetic SSE re-streaming from cache
The system SHALL replay cached streaming responses as a sequence of SSE `data:` lines, byte-for-byte identical to the original upstream response, delivered via `text/event-stream` content type.

#### Scenario: Cache hit replays SSE stream
- **WHEN** a streaming request results in a cache HIT
- **THEN** the system SHALL return a `StreamingResponse` with `media_type="text/event-stream"` that yields the cached SSE bytes as chunks, indistinguishable from a live upstream response

#### Scenario: Cache hit for non-streaming request
- **WHEN** a non-streaming request results in a cache HIT
- **THEN** the system SHALL return the cached JSON response body as a `JSONResponse` with the same structure as the original upstream response

### Requirement: Cache status response headers
The system SHALL attach an `X-Cache` header to every chat completion response indicating whether the response was served from cache.

#### Scenario: Cache hit includes HIT header
- **WHEN** a request is served from the cache
- **THEN** the response SHALL include the header `X-Cache: HIT`

#### Scenario: Cache miss includes MISS header
- **WHEN** a request is forwarded to the upstream provider (cache miss)
- **THEN** the response SHALL include the header `X-Cache: MISS`

#### Scenario: Cache disabled includes BYPASS header
- **WHEN** caching is disabled via configuration
- **THEN** the response SHALL include the header `X-Cache: BYPASS`
