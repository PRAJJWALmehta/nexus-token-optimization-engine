## Why

We need to empirically validate the token optimization engine's caching mechanisms (such as the semantic router, prompt compression, and graph-based retrieval). Currently, we lack a standardized, reliable way to simulate realistic or adversarial workloads, making it difficult to measure cache hit rates, throughput, and Time To First Token (TTFT).

> [!NOTE]
> **Refined approach based on feedback:** To ensure a realistic and low cache hit rate (<5%), we will use research sub-agents as a *one-time offline process* to scrape the web and construct a highly varied dataset of dummy requests. This static JSON/JSONL dataset will then be used by the benchmark suite at runtime. This avoids the slowness and unreliability of real-time web scraping during benchmark execution while still meeting the requirement for rich, agent-harvested data.

## What Changes

- Create a one-time data collection script/agent that scrapes various web sources to compile a high-entropy dataset of requests.
- Create a `benchmark_runner` script that loads this static dataset and dispatches test workloads against the engine.
- Implement an optional injection strategy to randomize prompts further (e.g., UUID injection) to deterministically ensure a <5% cache hit rate for baseline benchmarking if the dataset alone isn't enough.
- Output benchmark results (throughput, latency, cache hits/misses) to a structured report.

## Capabilities

### New Capabilities
- `benchmark-suite`: A reproducible benchmarking framework for testing throughput, latency, and cache hit rates using randomized datasets.

### Modified Capabilities

None.

## Impact

- Adds new development tooling for testing performance.
- Does not modify existing production code, but will rely on the `demo_runner.py` or the gateway API.
- Will introduce a one-time data collection script/agent to generate test fixtures.
