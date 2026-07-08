## 1. Setup & CLI Interface

- [x] 1.1 Create the CLI script `scratch/benchmark_cli.py` with argument parsing for gateway URL, dataset path, requests count, concurrency, model, streaming flag, output HTML path, and auto-open bypass.
- [x] 1.2 Implement pre-flight checks verifying gateway connectivity and dataset file existence.

## 2. Request Dispatcher & Telemetry Capture

- [x] 2.1 Implement the asynchronous HTTP request loop with semaphore-based concurrency control using `httpx`.
- [x] 2.2 Parse custom response headers (`X-Cache`, `X-Tokens-Saved`, `X-Routed-Model`, `X-Cached-Model`, `X-Pruning-Applied`) and output response length to build a detailed run telemetry dataset.

## 3. Cost & ROI Analytical Calculator

- [x] 3.1 Implement the baseline cost calculation logic (Opus pricing for all prompt and completion tokens).
- [x] 3.2 Implement optimized cost calculation logic (caching = $0, routing = Sonnet pricing for low complexity, pruning = cost of saved tokens removed).

## 4. Scorecard Dashboard Template & Generator

- [x] 4.1 Write the dark-mode, responsive HTML template with embedded styling, donut gradients, and count-up animations.
- [x] 4.2 Populate the template with run results, save the report to `scratch/benchmark_report.html`, and open it in the default browser.
