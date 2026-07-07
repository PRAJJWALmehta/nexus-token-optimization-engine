## Context

The Nexus Token-Optimization Gateway sits between LLM clients and upstream providers, implementing caching, pruning, and routing. While we have Prometheus and Grafana for operational telemetry, demonstrating the value of these optimization layers in a live interview requires an interactive, self-contained ROI scorecard.

## Goals / Non-Goals

**Goals:**
- Implement a Python CLI `scratch/benchmark_cli.py` that sends a configured number of concurrent requests through the gateway.
- Collect metadata from response headers (`X-Cache`, `X-Tokens-Saved`, `X-Routed-Model`, `X-Cached-Model`, `X-Pruning-Applied`) to analytically calculate baseline vs. optimized costs and token savings.
- Generate a single, offline-compatible, dark-themed HTML report `scratch/benchmark_report.html` presenting cost, token, latency, routing, cache, and pruning details using custom CSS/HTML charts.
- Auto-open the report in the user's browser.

**Non-Goals:**
- Modifying production gateway code under `src/` to support bypassing or telemetry headers (headers are already present).
- Running a two-pass benchmark (analytical cost calculation is used instead to avoid duplicate API calls and double execution times).
- Adding external charting libraries or CDNs (CSS `conic-gradient` and styled bar components will be used for offline safety).

## Decisions

### 1. Single-Pass Analytical Cost Calculation
- **Choice**: Analyze response headers to compute the baseline and optimized costs rather than running separate direct-to-upstream and through-gateway runs.
- **Rationale**: Saves time, costs fewer tokens, and prevents cached items from inflating the baseline run. Since we have original tokens, pruned tokens, and model choices recorded in headers, we can compute the cost delta deterministically.
- **Alternatives Considered**: Double-pass benchmark runner (slow, expensive, state-dependent).

### 2. Dependency-Free HTML/CSS Dashboard Output
- **Choice**: Use native CSS (gradients, flexbox, grid, keyframe animations) to render donut charts, bars, and cards in the HTML report.
- **Rationale**: Completely self-contained, launches instantly in offline environments, and has zero external dependencies or CDN constraints.
- **Alternatives Considered**: importing Chart.js/D3 via CDN (requires network connection, increases bundle size).

## Risks / Trade-offs

- **[Risk]** Target Gateway is offline → **[Mitigation]** The CLI will test connection to the gateway first and exit early with a helpful prompt if unreachable.
- **[Risk]** Output file write failure → **[Mitigation]** Standard fallback error trapping with stdout JSON summary output if file writing fails.
