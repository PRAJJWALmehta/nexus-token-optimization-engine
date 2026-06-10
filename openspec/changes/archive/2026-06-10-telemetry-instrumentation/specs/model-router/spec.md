## MODIFIED Requirements

### Requirement: Model routing for auto-selected model
The system SHALL provide a model router that intercepts requests with a trigger model name and resolves them to a concrete model based on complexity classification. The router SHALL mutate the request's `model` field in place and SHALL increment the `requests_per_model` metric for the resolved model.

#### Scenario: Trigger model activates routing
- **WHEN** a request has `model` set to the configured trigger name (default: `"auto"`)
- **THEN** the router SHALL classify the request complexity, replace the `model` field in place with the appropriate target model, and return a routing result containing the resolved model name
- **AND** the system SHALL increment the `requests_per_model` metric labeled with the resolved target model

#### Scenario: Non-trigger model bypasses routing
- **WHEN** a request has `model` set to any value other than the configured trigger name
- **THEN** the router SHALL NOT modify the request and SHALL return a routing result with `routed_model` set to `None`
- **AND** the system SHALL increment the `requests_per_model` metric labeled with the original requested model

#### Scenario: Low complexity routes to cheap model
- **WHEN** the router processes a trigger-model request AND the complexity classifier returns `low`
- **THEN** the router SHALL set the request `model` to the configured low-complexity model (default: `claude-sonnet-4-20250514`)
- **AND** the system SHALL increment `requests_per_model` with `model_name="claude-sonnet-4-20250514"`

#### Scenario: High complexity routes to capable model
- **WHEN** the router processes a trigger-model request AND the complexity classifier returns `high`
- **THEN** the router SHALL set the request `model` to the configured high-complexity model (default: `claude-opus-4-0520`)
- **AND** the system SHALL increment `requests_per_model` with `model_name="claude-opus-4-0520"`
