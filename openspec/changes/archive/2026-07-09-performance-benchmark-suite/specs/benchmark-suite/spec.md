## ADDED Requirements

### Requirement: Benchmark CLI Initialization
The system SHALL provide a command-line interface to start the benchmark suite.

#### Scenario: Running the benchmark suite
- **WHEN** the user executes the benchmark CLI command with a dataset name
- **THEN** the suite initializes the dataset stream and prepares load generation

### Requirement: Deterministic Low Cache Hit Rate Injection
The system SHALL provide a configurable mechanism to inject entropy into prompts.

#### Scenario: Ensuring cache hit rate < 5%
- **WHEN** the user configures the suite with `entropy=high`
- **THEN** the suite injects a unique UUID or timestamp into every request payload, ensuring that the semantic router and exact-match cache register misses >95% of the time.

### Requirement: Metric Reporting
The system SHALL report performance metrics after completing the benchmark run.

#### Scenario: Benchmark completion
- **WHEN** the requested number of load iterations finishes
- **THEN** the suite outputs a report detailing average latency, cache hit rate, and queries per second (QPS).
