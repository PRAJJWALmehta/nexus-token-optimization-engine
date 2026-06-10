## 1. Setup

- [x] 1.1 Add `prometheus-client` dependency to the project configuration (e.g. `pyproject.toml` or `requirements.txt`)
- [x] 1.2 Create a telemetry module to define all Prometheus metrics (`cache_hits_total`, `cache_misses_total`, `tokens_saved_total`, `gateway_latency_seconds`, `provider_latency_seconds`, `requests_per_model`)
- [x] 1.3 Update the main application to expose the `/metrics` endpoint

## 2. Telemetry Instrumentation

- [x] 2.1 Update the model router to increment the `requests_per_model` metric (labeled with the model name)
- [x] 2.2 Update the semantic cache lookup to increment `cache_hits_total` or `cache_misses_total`
- [x] 2.3 Update the semantic cache lookup to increment `tokens_saved_total` upon a cache hit
- [x] 2.4 Update the chat proxy endpoint to record `provider_latency_seconds` for upstream provider calls
- [x] 2.5 Update the chat proxy endpoint to record overall `gateway_latency_seconds` for all requests

## 3. Testing and Verification

- [x] 3.1 Write a test that simulates API traffic (routing, cache hits/misses) and scrapes the `/metrics` endpoint
- [x] 3.2 Verify that all Prometheus metrics increment and record data correctly according to the traffic generated

## 4. Observability Infrastructure

- [x] 4.1 Update `docker-compose.yml` to include a Prometheus service that scrapes the app's `/metrics` endpoint
- [x] 4.2 Update `docker-compose.yml` to include a Grafana service connected to the Prometheus data source
- [x] 4.3 Create a pre-configured `grafana-dashboard.json` specifically designed for token optimization metrics (savings, hit rates, latency)
