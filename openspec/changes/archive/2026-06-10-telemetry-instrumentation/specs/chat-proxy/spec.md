## MODIFIED Requirements

### Requirement: OpenAI-compatible chat completions endpoint
The system SHALL expose a `POST /v1/chat/completions` endpoint that accepts request bodies conforming to the OpenAI Chat Completions API schema. When the request model matches the routing trigger, the endpoint SHALL invoke the model router to resolve the concrete model before performing the semantic cache lookup. When pruning is enabled, the endpoint SHALL invoke the pruning pipeline after model routing but before the semantic cache lookup. When caching is enabled, the endpoint SHALL perform a semantic cache lookup before forwarding the request to the upstream provider. The endpoint SHALL record the overall gateway latency and, if applicable, the provider latency using the telemetry capability.

#### Scenario: Non-streaming request forwarded and response returned
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": false`
- **THEN** the system SHALL forward the request to the configured upstream provider and return the complete JSON response with the same status code
- **AND** the system SHALL record the duration of the upstream call in `provider_latency_seconds` and the total request duration in `gateway_latency_seconds`

#### Scenario: Streaming request forwarded and SSE response streamed
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": true`
- **THEN** the system SHALL forward the request to the upstream provider and stream back the response as `text/event-stream` SSE, including all `data:` lines and the final `data: [DONE]` sentinel
- **AND** the system SHALL record the duration of the upstream call in `provider_latency_seconds` and the total request duration in `gateway_latency_seconds`

#### Scenario: Malformed request body rejected
- **WHEN** a client sends a `POST /v1/chat/completions` request with an invalid body (e.g., missing `messages` field)
- **THEN** the system SHALL return a `422 Unprocessable Entity` response with a JSON error body describing the validation failure
- **AND** the system SHALL record the total request duration in `gateway_latency_seconds`

#### Scenario: Cache hit skips upstream call for streaming request
- **WHEN** a client sends a valid streaming request AND the semantic cache returns a HIT
- **THEN** the system SHALL NOT forward the request to the upstream provider and SHALL instead replay the cached response as synthetic SSE with an `X-Cache: HIT` header
- **AND** the system SHALL record the total request duration in `gateway_latency_seconds` without recording `provider_latency_seconds`

#### Scenario: Cache hit skips upstream call for non-streaming request
- **WHEN** a client sends a valid non-streaming request AND the semantic cache returns a HIT
- **THEN** the system SHALL NOT forward the request to the upstream provider and SHALL instead return the cached JSON response with an `X-Cache: HIT` header
- **AND** the system SHALL record the total request duration in `gateway_latency_seconds` without recording `provider_latency_seconds`

#### Scenario: Cache miss forwards to upstream with response buffering
- **WHEN** a client sends a valid request AND the semantic cache returns a MISS
- **THEN** the system SHALL forward the request to the upstream provider, buffer the response for cache storage, and include an `X-Cache: MISS` header in the response
- **AND** the system SHALL record both `provider_latency_seconds` and `gateway_latency_seconds`

#### Scenario: Routed request resolves model before cache lookup
- **WHEN** a client sends a valid request with `model` set to the routing trigger name AND routing is enabled
- **THEN** the system SHALL resolve the model via the model router BEFORE performing any cache lookup, so the resolved model is used as part of the cache key

#### Scenario: Routed request with cache MISS includes X-Routed-Model header
- **WHEN** a request was routed to a resolved model AND the response is served from upstream (cache MISS or BYPASS)
- **THEN** the response SHALL include an `X-Routed-Model` header with the resolved model name, in addition to the `X-Cache` header

#### Scenario: Routed request with cache HIT includes X-Cached-Model header
- **WHEN** a request was routed to a resolved model AND the response is served from cache (cache HIT)
- **THEN** the response SHALL include an `X-Cached-Model` header with the resolved model name instead of `X-Routed-Model`, in addition to the `X-Cache: HIT` header

#### Scenario: Pruned request processed before cache lookup
- **WHEN** a client sends a valid request AND pruning is enabled
- **THEN** the system SHALL apply the pruning pipeline to the request AFTER model routing but BEFORE cache lookup, so the cache key is computed on pruned content

#### Scenario: Pruning headers included in response
- **WHEN** the pruning pipeline runs and produces token savings
- **THEN** the response SHALL include `X-Tokens-Saved` and `X-Pruning-Applied` headers in addition to any routing and cache headers

#### Scenario: Pruning disabled does not add headers
- **WHEN** pruning is globally disabled via `PRUNING_ENABLED=false`
- **THEN** the response SHALL NOT include `X-Tokens-Saved` or `X-Pruning-Applied` headers
