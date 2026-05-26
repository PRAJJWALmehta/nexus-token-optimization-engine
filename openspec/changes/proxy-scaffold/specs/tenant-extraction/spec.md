## ADDED Requirements

### Requirement: Tenant ID extraction from API key
The system SHALL extract a tenant identifier from every incoming request by parsing the `Authorization: Bearer <key>` header.

#### Scenario: API key with tenant prefix
- **WHEN** a request contains `Authorization: Bearer tenantABC_sk-rest-of-key`
- **THEN** the system SHALL extract `tenantABC` as the tenant ID (the segment before the first `_` delimiter) and attach it to the request state

#### Scenario: API key without tenant prefix
- **WHEN** a request contains `Authorization: Bearer sk-no-prefix-key` (no `_` delimiter in the key)
- **THEN** the system SHALL assign the tenant ID `default` and attach it to the request state

#### Scenario: Missing Authorization header
- **WHEN** a request does not contain an `Authorization` header
- **THEN** the system SHALL assign the tenant ID `default` and proceed (no authentication enforcement in Phase 1)

### Requirement: Tenant ID availability in request lifecycle
The tenant ID SHALL be available to all downstream handlers via `request.state.tenant_id` for the duration of the request.

#### Scenario: Downstream handler reads tenant ID
- **WHEN** a request has been processed by the tenant extraction middleware
- **THEN** any downstream route handler SHALL be able to read `request.state.tenant_id` and receive the extracted or default tenant ID string
