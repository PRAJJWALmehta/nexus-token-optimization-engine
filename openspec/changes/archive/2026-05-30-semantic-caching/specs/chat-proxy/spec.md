## MODIFIED Requirements

### Requirement: OpenAI-compatible chat completions endpoint
The system SHALL expose a `POST /v1/chat/completions` endpoint that accepts request bodies conforming to the OpenAI Chat Completions API schema. When caching is enabled, the endpoint SHALL perform a semantic cache lookup before forwarding the request to the upstream provider.

#### Scenario: Non-streaming request forwarded and response returned
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": false`
- **THEN** the system SHALL forward the request to the configured upstream provider and return the complete JSON response with the same status code

#### Scenario: Streaming request forwarded and SSE response streamed
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": true`
- **THEN** the system SHALL forward the request to the upstream provider and stream back the response as `text/event-stream` SSE, including all `data:` lines and the final `data: [DONE]` sentinel

#### Scenario: Malformed request body rejected
- **WHEN** a client sends a `POST /v1/chat/completions` request with an invalid body (e.g., missing `messages` field)
- **THEN** the system SHALL return a `422 Unprocessable Entity` response with a JSON error body describing the validation failure

#### Scenario: Cache hit skips upstream call for streaming request
- **WHEN** a client sends a valid streaming request AND the semantic cache returns a HIT
- **THEN** the system SHALL NOT forward the request to the upstream provider and SHALL instead replay the cached response as synthetic SSE with an `X-Cache: HIT` header

#### Scenario: Cache hit skips upstream call for non-streaming request
- **WHEN** a client sends a valid non-streaming request AND the semantic cache returns a HIT
- **THEN** the system SHALL NOT forward the request to the upstream provider and SHALL instead return the cached JSON response with an `X-Cache: HIT` header

#### Scenario: Cache miss forwards to upstream with response buffering
- **WHEN** a client sends a valid request AND the semantic cache returns a MISS
- **THEN** the system SHALL forward the request to the upstream provider, buffer the response for cache storage, and include an `X-Cache: MISS` header in the response
