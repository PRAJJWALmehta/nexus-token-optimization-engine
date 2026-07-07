## Why

To maximize the interview value of the Nexus Token-Optimization Gateway, we need a way to easily demonstrate and visualize the cost, token, and latency savings in a single command. This change introduces a CLI-based performance benchmark tool that analytically computes ROI metrics and generates a self-contained, interactive HTML scorecard report for stakeholders.

## What Changes

- Add a new script `scratch/benchmark_cli.py` which executes concurrent request runs through the gateway.
- Add analytical cost calculation based on response telemetry headers (`X-Cache`, `X-Tokens-Saved`, `X-Routed-Model`, `X-Cached-Model`).
- Generate a self-contained, responsive, dark-mode `scratch/benchmark_report.html` scorecard (with animated totals, custom CSS charts for cache, routing, pruning, and latency profiles).
- Add support for configuration via CLI flags (`--url`, `--dataset`, `--requests`, `--concurrency`, `--model`, `--stream`, `--output`, `--no-open`).

## Capabilities

### New Capabilities
- `benchmark-scorecard-generator`: The ability to run concurrent benchmark sessions through the gateway, capture telemetry headers, analytically calculate USD costs/savings against a raw upstream baseline, and render a self-contained HTML/JS dashboard representing performance/ROI metrics.

### Modified Capabilities
*(None)*

## Impact

- **Production Code**: No impact. Production code paths (`src/`) are unchanged.
- **Dependencies**: No new external dependencies. Standard library and existing dependency (`httpx`) are used.
- **Files Created**: `scratch/benchmark_cli.py` and the dynamically generated `scratch/benchmark_report.html` (which is excluded from Git tracking).
