# benchmark-suite Specification

## Purpose
TBD - created by archiving change performance-benchmark-suite. Update Purpose after archive.
## Requirements
### Requirement: Benchmark CLI Initialization
The system SHALL provide a command-line interface to start the benchmark suite, supporting both fixed-request count and continuous execution modes.

#### Scenario: Running the benchmark suite in fixed mode
- **WHEN** the user executes the benchmark CLI command with a fixed request count
- **THEN** the suite initializes the dataset stream and prepares load generation

### Requirement: Continuous Execution with Keep-Alive
The system SHALL support continuous load generation until stopped, with a periodic prompt checking if the run should continue.

#### Scenario: Running the benchmark suite in continuous mode
- **WHEN** the user executes the benchmark CLI command with the `--continuous` option
- **THEN** the suite runs continuously and prompts the user every hour to confirm continuation, exiting if declined or timed out.

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

### Requirement: Cache Hit Rate Constraint under High Entropy
The system SHALL guarantee that the measured cache hit rate is between 1% and 5% (inclusive) when high entropy is configured and the total requests are at least 20.

#### Scenario: Cache hit rate constraint verification
- **WHEN** the benchmark runner completes a run of at least 20 requests with `--entropy high`
- **THEN** the reported Measured Cache Hit Rate SHALL be between 1.0% and 5.0% (inclusive).

