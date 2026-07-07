## ADDED Requirements

### Requirement: Benchmark Execution & Concurrency
The system SHALL support launching a concurrent benchmark run sending a specified number of requests to the gateway using an asynchronous HTTP client.

#### Scenario: Benchmark execution
- **WHEN** the benchmark CLI is invoked with `--requests 30 --concurrency 5`
- **THEN** the system SHALL dispatch exactly 30 requests to the target gateway URL using an HTTPX async client with a concurrency limit of 5.

### Requirement: Analytical Cost Calculation
The system SHALL collect telemetry headers from the gateway's response and analytically compute the cost savings against a raw upstream baseline.

#### Scenario: Cost calculation for cache hit
- **WHEN** a request response carries `X-Cache: HIT`, `X-Tokens-Saved: 400`, `X-Cached-Model: claude-sonnet-4-20250514`
- **THEN** the system SHALL calculate the baseline cost using Opus pricing on original tokens and the optimized cost as $0.

#### Scenario: Cost calculation for cache miss
- **WHEN** a request response carries `X-Cache: MISS`, `X-Tokens-Saved: 200`, `X-Routed-Model: claude-sonnet-4-20250514`
- **THEN** the system SHALL calculate the baseline cost using Opus pricing on original tokens and the optimized cost using Sonnet pricing on pruned tokens (original - saved).

### Requirement: Self-Contained HTML Scorecard Generation
The system SHALL generate a self-contained, offline-compatible HTML file containing the benchmark results.

#### Scenario: Report file generation
- **WHEN** the benchmark run completes
- **THEN** the system SHALL write a styled HTML file containing inline CSS and JS, populating the cost reduction percentage, tokens saved, cache hits/misses distribution, routing distribution, pruning breakdown, and latency profile, and attempt to open it in a web browser.
