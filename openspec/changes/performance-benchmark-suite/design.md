## Context

Currently, the engine relies on simple dummy test files (like `demo_runner.py`) or manual requests to test the cache implementations (prefix, KV, semantic routing). We do not have an automated mechanism to load high-throughput traffic, generate complex payloads, and measure key metrics like cache hit rate, end-to-end latency, and throughput. To systematically test our prompt compression and pruning logic, we need reproducible and controllable inputs.

## Goals / Non-Goals

**Goals:**
- Provide a CLI-based benchmark suite for load generation.
- Use an offline data collection script/agent to scrape web sources once and create a static dataset of highly varied dummy requests.
- Load the generated static dataset to provide realistic test data during benchmark execution.
- Inject dynamic entropy (e.g. UUIDs, timestamp strings, noise) into prompts to explicitly guarantee a <5% cache hit rate when needed, if the dataset itself isn't diverse enough.
- Collect, aggregate, and report metrics (e.g. latency, throughput).

**Non-Goals:**
- Replacing existing unit or integration tests.
- Simulating a distributed cluster. This is meant to test a single engine instance.
- Running web-scraping sub-agents dynamically during the actual benchmark execution.

## Decisions

1. **One-Time Offline Data Collection via Agents**:
   - *Rationale*: Running sub-agents at runtime introduces network unreliability and latency, which makes benchmark runs slow, non-deterministic, and flaky. By running the sub-agents once offline to scrape the web and build a massive static JSON/JSONL dataset, we ensure rapid, deterministic, and repeatable benchmark runs while still benefiting from the rich, unconstrained variety of web-scraped requests. 
   - *Alternative*: Real-time sub-agents (rejected due to latency/flakiness) or static HuggingFace datasets (rejected because we specifically want agent-curated web scrapes).
2. **Entropy Injection for Cache Busting**:
   - *Rationale*: Even with a large diverse dataset, we might occasionally hit the cache or want to explicitly test extreme cache-miss scenarios. Injecting unique UUIDs or timestamps directly into the text payloads bypasses semantic and exact-match caching reliably.
   - *Alternative*: Relying solely on the dataset's natural variety. This is harder to guarantee mathematically across millions of requests. Simple token-level injection is faster and 100% effective as an optional toggle.
3. **Data format**:
   - *Rationale*: The benchmark will structure its payloads exactly as expected by the existing `demo_runner.py` or the gateway API (e.g. `messages` array).

## Risks / Trade-offs

- **Risk: Entropy injection doesn't bypass Semantic Cache.**
  - *Mitigation*: Ensure the injection of UUIDs or large salt strings is prominent enough (e.g., at the start of the prompt) to alter the embedding significantly, bypassing cosine similarity thresholds.
- **Risk: Offline dataset generation fails or takes too long.**
  - *Mitigation*: The generation script should support chunking and resuming so that progress is saved intermittently (e.g., streaming to a JSONL file).
