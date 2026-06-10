# Nexus Token-Optimization Gateway: Future Roadmap & Postponed Tasks

This document tracks design decisions, enhancements, and features that have been explicitly postponed to future development phases of the Nexus gateway.

---

## 📋 Postponed Features & Phases

### Phase 2–4: Optimization Engine
- [x] **Prompt Caching**: Cache repeated prompts per tenant to avoid redundant upstream execution and save cost.
- [x] **Prompt Pruning**: Prune redundant tokens/messages from prompt histories before forwarding to the upstream model.
- [ ] **Aggressive Prompt Pruning**: Make compression more aggressive by lowering the default pruning token budget (e.g., to 4,000/8,000 tokens), stripping docstrings from code blocks, and removing HTML/Markdown comments globally.
- [ ] **Request Modification**: Dynamically inject custom headers or parameters into upstream payloads.

### Phase 3: Routing & Cost Optimization
- [x] **Multi-Model Routing**: Implement intelligent request routing (e.g., route simpler prompts to cheaper models like GPT-4o-mini and complex prompts to GPT-4o).
- [ ] **Cost Tracking & Budgeting**: Monitor token usage per tenant and apply rate limiting or budget enforcement when thresholds are exceeded.

### Phase 5: Observability & Telemetry
- [x] **Metrics Integration**: Export Prometheus metrics tracking latency, token usage, request counts, cache hit/miss rates, and error frequencies.
- [ ] **Grafana Dashboard Revamp**: Revamp layout into Executive ROI (savings breakdown, Cache vs Pruning ROI) and Ops views (P95/P99 latency, Cache Hit vs Miss latency, routing distribution stacked over time).
- [ ] **OpenTelemetry Tracing**: Implement tracing to monitor the end-to-end request lifecycle and upstream performance.

---

## 🛠️ Postponed Architectural & Infrastructure Enhancements

### Authentication & Authorization
- [ ] **Robust Auth System**: Transition from simple prefix-based tenant extraction (`tenantID_sk-key`) to a proper authentication mechanism (e.g., JWT validation, OAuth2, or API key database lookups).

### Upstream Providers
- [ ] **Native Anthropic Adapter**: Implement `AnthropicProviderAdapter` supporting Anthropic's proprietary protocol (converting inputs/outputs to keep the gateway transparent).
- [ ] **Custom LLM Endpoint Adapter**: Add configuration support for local models or alternative inference APIs (e.g., Ollama, vLLM).

### Persistence & Storage
- [ ] **Database Setup**: Introduce a data store (like Redis for caching, PostgreSQL/Redis for rate-limiting counters and tenant metadata storage).

### Operations & CI/CD
- [x] **Dockerization**: Create a `Dockerfile` and `docker-compose.yml` for simplified orchestration (using OrbStack).
- [ ] **CI/CD Pipeline**: Configure GitHub Actions for linting, automated testing, and deployment.
- [ ] **Production Deployment Configuration**: Define production-ready Uvicorn settings, reverse proxy settings (like Nginx/Traefik), and TLS/HTTPS configuration.
