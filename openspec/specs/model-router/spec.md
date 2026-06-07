## ADDED Requirements

### Requirement: Model routing for auto-selected model
The system SHALL provide a model router that intercepts requests with a trigger model name and resolves them to a concrete model based on complexity classification. The router SHALL mutate the request's `model` field in place.

#### Scenario: Trigger model activates routing
- **WHEN** a request has `model` set to the configured trigger name (default: `"auto"`)
- **THEN** the router SHALL classify the request complexity, replace the `model` field in place with the appropriate target model, and return a routing result containing the resolved model name

#### Scenario: Non-trigger model bypasses routing
- **WHEN** a request has `model` set to any value other than the configured trigger name
- **THEN** the router SHALL NOT modify the request and SHALL return a routing result with `routed_model` set to `None`

#### Scenario: Low complexity routes to cheap model
- **WHEN** the router processes a trigger-model request AND the complexity classifier returns `low`
- **THEN** the router SHALL set the request `model` to the configured low-complexity model (default: `claude-sonnet-4-20250514`)

#### Scenario: High complexity routes to capable model
- **WHEN** the router processes a trigger-model request AND the complexity classifier returns `high`
- **THEN** the router SHALL set the request `model` to the configured high-complexity model (default: `claude-opus-4-0520`)

### Requirement: Routing configuration via environment variables
The model router SHALL read all routing parameters from environment variables or application settings.

#### Scenario: Custom trigger model name
- **WHEN** `ROUTING_TRIGGER_MODEL` is set to `"nexus-auto"`
- **THEN** the router SHALL activate only for requests with `model: "nexus-auto"`

#### Scenario: Default trigger model name
- **WHEN** `ROUTING_TRIGGER_MODEL` is not set
- **THEN** the router SHALL use `"auto"` as the trigger model name

#### Scenario: Custom model mappings
- **WHEN** `ROUTING_LOW_MODEL` is set to `"gpt-4o-mini"` and `ROUTING_HIGH_MODEL` is set to `"gpt-4o"`
- **THEN** the router SHALL route low-complexity requests to `"gpt-4o-mini"` and high-complexity requests to `"gpt-4o"`

#### Scenario: Default model mappings
- **WHEN** `ROUTING_LOW_MODEL` and `ROUTING_HIGH_MODEL` are not set
- **THEN** the router SHALL use `"claude-sonnet-4-20250514"` for low-complexity and `"claude-opus-4-0520"` for high-complexity requests

### Requirement: Routing observability headers
The system SHALL include routing metadata in the response so clients can observe which model was selected and how the response was served.

#### Scenario: Routed request with cache MISS includes X-Routed-Model header
- **WHEN** a request was routed (trigger model was matched and resolved) AND the response is served from the upstream (cache MISS or BYPASS)
- **THEN** the response SHALL include an `X-Routed-Model` header with the resolved model name

#### Scenario: Routed request with cache HIT includes X-Cached-Model header
- **WHEN** a request was routed AND the response is served from cache (cache HIT)
- **THEN** the response SHALL include an `X-Cached-Model` header with the resolved model name instead of `X-Routed-Model`

#### Scenario: Non-routed request omits routing headers
- **WHEN** a request was not routed (model was not the trigger name)
- **THEN** the response SHALL NOT include `X-Routed-Model` or `X-Cached-Model` headers

### Requirement: Routing decision logging
The system SHALL log every routing decision at INFO level with structured fields for traceability and pre-telemetry analytics.

#### Scenario: Routing decision logged on resolve
- **WHEN** the router processes a trigger-model request and resolves a concrete model
- **THEN** the system SHALL log at INFO level including: original model name, resolved model name, complexity level, estimated token count, and keyword match (if any)

#### Scenario: Non-routed request not logged
- **WHEN** the router receives a request that does not match the trigger model
- **THEN** the system SHALL NOT log a routing decision

### Requirement: Routing enabled toggle
The system SHALL allow routing to be globally disabled via the `ROUTING_ENABLED` environment variable.

#### Scenario: Routing disabled rejects trigger model requests
- **WHEN** `ROUTING_ENABLED` is set to `false` AND a request has `model` set to the trigger name
- **THEN** the router SHALL reject the request with a `400 Bad Request` response containing the message `"Dynamic routing is disabled; specify a concrete model name"`

#### Scenario: Routing disabled passes non-trigger requests
- **WHEN** `ROUTING_ENABLED` is set to `false` AND a request has `model` set to a non-trigger name
- **THEN** the router SHALL NOT modify the request and SHALL return it unchanged

#### Scenario: Routing enabled by default
- **WHEN** `ROUTING_ENABLED` is not set
- **THEN** routing SHALL be enabled
