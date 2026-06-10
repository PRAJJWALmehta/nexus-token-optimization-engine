## Why

To quantify the value of the token optimization engine, we need visibility into its performance and savings. Implementing telemetry and observability will allow us to measure critical metrics such as cost savings, latency overhead, and cache hit rates.

## What Changes

- Add Prometheus counters for cache performance (`cache_hits_total`, `cache_misses_total`) and savings (`tokens_saved_total`).
- Add Prometheus histograms to track latency overhead (`gateway_latency_seconds`) and provider latency (`provider_latency_seconds`).
- Add a routing distribution gauge to monitor requests per model.
- Expose a `/metrics` endpoint for Prometheus to scrape.
- Ensure test traffic generates metric increments correctly.

## Capabilities

### New Capabilities
- `telemetry`: Instrumenting the application with Prometheus metrics to measure savings, latency, and cache hit rates, and exposing a `/metrics` endpoint.

### Modified Capabilities
- `chat-proxy`: Requires integration with the telemetry capability to track overall and provider latency.
- `model-router`: Requires integration with the telemetry capability to track requests per model.
- `cache-lookup`: Requires integration with telemetry to track cache hits, misses, and tokens saved.

## Impact

- **Code:** New telemetry module/functions will be added. Existing routing, proxy, and cache modules will be instrumented.
- **APIs:** A new `/metrics` HTTP endpoint will be exposed on the gateway.
- **Dependencies:** Will introduce a Prometheus client library dependency (e.g., `prometheus_client` for Python).
- **Systems:** Prometheus (or a compatible metrics scraper) will need network access to the new `/metrics` endpoint.
