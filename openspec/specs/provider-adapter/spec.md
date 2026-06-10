## ADDED Requirements

### Requirement: Provider adapter protocol
The system SHALL define a `ProviderAdapter` abstract base class (protocol) with a method `stream_completions(request: ChatCompletionRequest) → AsyncIterator[bytes]` that all provider implementations MUST conform to.

#### Scenario: New provider implementation conformance
- **WHEN** a developer creates a new provider adapter class
- **THEN** the class MUST implement `stream_completions` accepting a `ChatCompletionRequest` and returning an `AsyncIterator[bytes]` yielding raw SSE byte chunks

### Requirement: OpenAI-compatible provider adapter
The system SHALL implement an `OpenAIProviderAdapter` that forwards requests to any OpenAI-compatible API endpoint and streams back SSE responses.

#### Scenario: Successful streaming completion
- **WHEN** `OpenAIProviderAdapter.stream_completions()` is called with a valid request
- **THEN** the adapter SHALL send an HTTP POST to the configured upstream API URL with the serialized request body, set the appropriate `Authorization` and `Content-Type` headers, and yield each SSE line from the upstream response as raw bytes

#### Scenario: Upstream connection failure
- **WHEN** the adapter cannot connect to the upstream API (e.g., DNS failure, connection refused)
- **THEN** the adapter SHALL raise an exception that the global exception handler catches and converts to a `502 Bad Gateway` response

#### Scenario: Upstream timeout
- **WHEN** the upstream API does not respond within the configured timeout period
- **THEN** the adapter SHALL raise a timeout exception that results in a `504 Gateway Timeout` response to the client

### Requirement: Provider configuration
The provider adapter SHALL read its configuration (upstream API URL, timeout) from environment variables or application settings.

#### Scenario: Custom upstream URL configured
- **WHEN** the environment variable `UPSTREAM_API_URL` is set to `https://custom.api.example.com/v1/chat/completions`
- **THEN** the `OpenAIProviderAdapter` SHALL use that URL for all upstream requests

#### Scenario: Default upstream URL
- **WHEN** no `UPSTREAM_API_URL` environment variable is set
- **THEN** the `OpenAIProviderAdapter` SHALL use `https://api.openai.com/v1/chat/completions` as the default upstream URL
