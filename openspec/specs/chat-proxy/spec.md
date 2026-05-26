## ADDED Requirements

### Requirement: OpenAI-compatible chat completions endpoint
The system SHALL expose a `POST /v1/chat/completions` endpoint that accepts request bodies conforming to the OpenAI Chat Completions API schema.

#### Scenario: Non-streaming request forwarded and response returned
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": false`
- **THEN** the system SHALL forward the request to the configured upstream provider and return the complete JSON response with the same status code

#### Scenario: Streaming request forwarded and SSE response streamed
- **WHEN** a client sends a valid `POST /v1/chat/completions` request with `"stream": true`
- **THEN** the system SHALL forward the request to the upstream provider and stream back the response as `text/event-stream` SSE, including all `data:` lines and the final `data: [DONE]` sentinel

#### Scenario: Malformed request body rejected
- **WHEN** a client sends a `POST /v1/chat/completions` request with an invalid body (e.g., missing `messages` field)
- **THEN** the system SHALL return a `422 Unprocessable Entity` response with a JSON error body describing the validation failure

### Requirement: Pydantic request and response models
The system SHALL define Pydantic models for `ChatCompletionRequest` and `ChatCompletionResponse` (including `ChatCompletionChunk` for streaming deltas) that mirror the OpenAI API schema.

#### Scenario: Request model validates required fields
- **WHEN** a request is deserialized into `ChatCompletionRequest`
- **THEN** the model SHALL require `model` (string) and `messages` (list of message objects with `role` and `content`), and SHALL accept optional fields including `temperature`, `max_tokens`, `stream`, `top_p`, `stop`, and `n`

#### Scenario: Extra fields are preserved for pass-through
- **WHEN** a request contains fields not explicitly defined in the Pydantic model (e.g., provider-specific extensions)
- **THEN** the model SHALL preserve those fields via `model_config = {"extra": "allow"}` so they are forwarded to the upstream provider without loss

### Requirement: Upstream error pass-through
The system SHALL forward upstream HTTP error responses to the client without modification, preserving both the status code and response body.

#### Scenario: Upstream returns 429 rate limit
- **WHEN** the upstream provider returns a `429 Too Many Requests` response
- **THEN** the system SHALL return a `429` response to the client with the upstream response body intact

#### Scenario: Upstream returns 500 server error
- **WHEN** the upstream provider returns a `500 Internal Server Error`
- **THEN** the system SHALL return a `500` response to the client with the upstream response body intact

### Requirement: Internal error handling
The system SHALL handle unexpected internal errors without crashing and SHALL return a structured JSON error response.

#### Scenario: Unhandled exception during request processing
- **WHEN** an unexpected exception occurs during request processing (e.g., connection refused to upstream)
- **THEN** the system SHALL return a `502 Bad Gateway` response with a JSON body containing `{"error": {"message": "<description>", "type": "gateway_error"}}`
