## Context

The token optimization engine currently lacks visibility into its operational metrics. We need to track cost savings (token usage), cache hit rates, and latency overhead to quantify the engine's value and diagnose performance issues. The system will expose a `/metrics` endpoint to be scraped by Prometheus.

## Goals / Non-Goals

**Goals:**
- Instrument core pathways (caching, routing, proxying) with Prometheus metrics.
- Expose a `/metrics` HTTP endpoint.
- Provide counters for cache hits/misses and tokens saved.
- Provide histograms for gateway and provider latency.
- Track requests per model using a gauge or counter.

**Non-Goals:**
- Creating custom metrics backends (sticking to standard Prometheus exposition format).
- Building an internal custom UI dashboard.

## Decisions

- **Prometheus Client Library**: Use `prometheus_client` library to define and expose metrics.
  *Rationale*: It is the standard Prometheus library for Python, easily integrated with modern async frameworks like FastAPI.
- **Metric Definitions**:
  - `cache_hits_total` (Counter)
  - `cache_misses_total` (Counter)
  - `tokens_saved_total` (Counter)
  - `gateway_latency_seconds` (Histogram)
  - `provider_latency_seconds` (Histogram)
  - `requests_per_model` (Gauge or Counter labeled by `model_name`)
- **Metrics Endpoint**: Host on `/metrics` by using `make_asgi_app()` from `prometheus_client` (or `generate_latest()`) mounted onto the main application router.
- **Labels**: We will keep labels low-cardinality. Specifically, we'll label metrics with `model_name` and potentially `status_code`, but avoid high-cardinality labels like request IDs.
- **Observability Infrastructure**: Extend the existing `docker-compose.yml` to include Prometheus and Grafana services. Provide a pre-configured Grafana dashboard JSON file for Token Optimization metrics.
  *Rationale*: Adopts the standard Infrastructure-as-a-Service approach, providing a robust observability stack with no internal state management overhead in the application.

## Risks / Trade-offs

- **Performance Overhead**: Tracking metrics (especially histograms) can introduce minor CPU overhead.
  *Mitigation*: Use standard buckets and avoid complex label structures.
- **Label Explosion**: Adding too many dynamic labels to Prometheus metrics can cause memory issues on the server and in Prometheus.
  *Mitigation*: Strictly restrict labels to known, low-cardinality sets (e.g., model names).
