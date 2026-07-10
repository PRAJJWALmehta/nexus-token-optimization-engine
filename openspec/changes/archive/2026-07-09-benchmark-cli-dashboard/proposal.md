## Why

To maximize the interview value of the Nexus Token-Optimization Gateway, we need a way to easily demonstrate and visualize the cost, token, and latency savings in a single command. This change introduces a CLI-based performance benchmark tool that analytically computes ROI metrics and generates a self-contained, interactive HTML scorecard report for stakeholders.

## What Changes

- Add a new script `scratch/benchmark_cli.py` which executes concurrent request runs through the gateway.
- Add a lightweight background FastAPI/Uvicorn server within `scratch/benchmark_cli.py` to host the HTML dashboard and push real-time progression updates via Server-Sent Events (SSE).
- Add analytical cost calculation based on response telemetry headers (`X-Cache`, `X-Tokens-Saved`, `X-Routed-Model`, `X-Cached-Model`).
- Generate a self-contained, responsive, dark-mode `scratch/benchmark_report.html` scorecard (with live-ticking stats and animated CSS charts for cache, routing, pruning, and latency profiles).
- Add support for configuration via CLI flags (`--url`, `--dataset`, `--requests`, `--concurrency`, `--model`, `--stream`, `--output`, `--no-open`, `--port`).

## Capabilities

### New Capabilities
- `benchmark-scorecard-generator`: The ability to run concurrent benchmark sessions through the gateway, capture telemetry headers, analytically calculate USD costs/savings against a raw upstream baseline, and host a live-updating HTML/JS dashboard via Server-Sent Events (SSE) representing performance/ROI metrics in real-time.

### Modified Capabilities
*(None)*

## Impact

- **Production Code**: No impact. Production code paths (`src/`) are unchanged.
- **Dependencies**: No new external dependencies. Standard library and existing dependencies (`httpx`, `fastapi`, `uvicorn`) are used.
- **Network**: Binds a temporary server on local port 8050 during benchmark execution.
- **Files Created**: `scratch/benchmark_cli.py` and the dynamically generated `scratch/benchmark_report.html`.
