## 1. Setup & Data Collection

- [x] 1.1 Create `data_collector.py` script to utilize web-scraping agents.
- [x] 1.2 Run the data collector once to compile a rich `dummy_requests.jsonl` fixture file.
- [x] 1.3 Create `benchmark_runner.py` scaffold.

## 2. Dataset Loading

- [x] 2.1 Implement a loader function in `benchmark_runner.py` that reads the static `dummy_requests.jsonl` file.
- [x] 2.2 Transform the loaded rows into the expected messages format for the engine.

## 3. Entropy Injection

- [x] 3.1 Implement a `inject_entropy` function that takes a payload and appends/prepends a UUID or random timestamp.
- [x] 3.2 Add CLI configuration (e.g., `--entropy=high`) to toggle this injection logic to guarantee a <5% cache hit rate.

## 4. Benchmark Runner Execution

- [x] 4.1 Implement a concurrency or loop mechanism to dispatch requests to the optimization engine or gateway.
- [x] 4.2 Track TTFT (Time To First Token), end-to-end latency, and record whether the response was a cache hit or miss.

## 5. Metrics & Reporting

- [x] 5.1 Implement a reporting mechanism to summarize QPS, average latency, and cache hit percentages at the end of the run.
- [x] 5.2 Validate the benchmark locally to ensure cache hit rate < 5% when entropy injection is enabled.

## 6. Continuous Execution & Keep-Alive

- [x] 6.1 Implement the `--continuous` CLI flag and worker loops in `benchmark_runner.py`.
- [x] 6.2 Implement periodic keep-alive checks (defaulting to hourly) with timeout prompts.
- [x] 6.3 Verify continuous mode behaves correctly with Ctrl+C and the keep-alive check.
