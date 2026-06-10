## ADDED Requirements

### Requirement: Health check endpoint
The system SHALL expose a `GET /health` endpoint that returns the operational status of the gateway.

#### Scenario: Gateway is healthy
- **WHEN** a client sends a `GET /health` request and the gateway is operational
- **THEN** the system SHALL return a `200 OK` response with a JSON body `{"status": "healthy"}`

#### Scenario: Health check response time
- **WHEN** a client sends a `GET /health` request
- **THEN** the system SHALL respond within 100ms (the endpoint MUST NOT perform upstream connectivity checks or I/O-bound operations)
