## ADDED Requirements

### Requirement: Prometheus metrics exposition endpoint
The system SHALL expose a GET `/metrics` endpoint that returns Prometheus-formatted metrics.

#### Scenario: Prometheus scrapes metrics
- **WHEN** a client sends a GET request to `/metrics`
- **THEN** the system SHALL return a `200 OK` response with `Content-Type: text/plain` (or appropriate versioned type) containing all registered Prometheus metrics

### Requirement: Core metrics registration
The system SHALL register and track core operational metrics: `cache_hits_total`, `cache_misses_total`, `tokens_saved_total`, `gateway_latency_seconds`, `provider_latency_seconds`, and `requests_per_model`.

#### Scenario: Metrics are initialized at startup
- **WHEN** the application starts
- **THEN** all defined metrics SHALL be registered with the Prometheus registry and initialized to 0 or empty structures
