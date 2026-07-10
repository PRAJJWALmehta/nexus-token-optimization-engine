# Benchmark CLI with HTML Scorecard Dashboard

A hybrid Python CLI tool that runs a benchmark workload through the Nexus gateway, collects per-request telemetry from response headers, analytically computes baseline vs. optimized costs, and generates a self-contained dark-mode HTML dashboard showing the ROI story.

## Motivation

The project has a fully operational gateway (caching, pruning, routing, telemetry) and a Grafana dashboard for real-time operational monitoring. What's missing is a **one-shot ROI scorecard** — a single command that produces an interview-ready, shareable artifact proving the cost savings.

## Architecture

```
                        benchmark_cli.py
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                     │
    BenchmarkSession    CostCalculator    ScoreCardRenderer
         │                    │                     │
    Fires N requests    Computes baseline     Renders self-contained
    via httpx async     vs optimized cost     HTML with inline CSS/JS
         │                    │                     │
         ▼                    │                     │
    Nexus Gateway (:8000)     │                     │
    Returns headers:          │                     │
      X-Cache                 │                     │
      X-Tokens-Saved          │                     │
      X-Routed-Model          │                     │
      X-Pruning-Applied       │                     │
         │                    │                     │
         └────────► List[RequestResult] ────────────┘
                   (per-request telemetry)
```

### Single-Pass Analytical Approach

The tool sends requests through the gateway **once** and uses response headers to compute both baseline and optimized costs analytically. No need for a separate "baseline" run.

- **Original tokens**: estimated from the request payload content (`len(content) // 4`)
- **Pruned tokens**: `original_tokens - X-Tokens-Saved`
- **Model used**: `X-Routed-Model` (MISS/BYPASS) or `X-Cached-Model` (HIT)
- **Cache status**: `X-Cache` header (HIT / MISS / BYPASS)

## Files

| File | Purpose |
|---|---|
| `scratch/benchmark_cli.py` | Python CLI — fires requests, collects telemetry, computes costs, generates HTML report |
| `scratch/benchmark_report.html` | Output artifact — self-contained dark-mode dashboard (generated, not committed) |

No changes to `src/` production code. No new dependencies beyond what's already in the project (`httpx`, `asyncio`, `argparse`).

## Data Collection

### Per-Request Telemetry

Each request through the gateway yields a `RequestResult`:

```python
@dataclass
class RequestResult:
    original_tokens: int       # len(request_content) // 4 (pre-pruning estimate)
    tokens_saved: int          # from X-Tokens-Saved header (0 if missing)
    cache_status: str          # from X-Cache: HIT / MISS / BYPASS
    routed_model: str          # from X-Routed-Model or X-Cached-Model
    latency_s: float           # client-side wall-clock measurement
    ttft_s: float | None       # first chunk arrival time (streaming only)
    transforms_applied: list   # from X-Pruning-Applied (split on comma)
    response_size: int         # response body bytes (for completion token estimate)
```

### Response Header Mapping

| Header | Field | Fallback |
|---|---|---|
| `X-Cache` | `cache_status` | `"BYPASS"` |
| `X-Tokens-Saved` | `tokens_saved` | `0` |
| `X-Routed-Model` | `routed_model` (MISS/BYPASS) | request model |
| `X-Cached-Model` | `routed_model` (HIT) | request model |
| `X-Pruning-Applied` | `transforms_applied` | `[]` |

## Cost Calculation

### Pricing Table

Matches `src/telemetry.py` constants:

| Model | Input ($/token) | Output ($/token) |
|---|---|---|
| `claude-opus-4-0520` | $0.000015 | $0.000075 |
| `claude-sonnet-4-20250514` | $0.000003 | $0.000015 |
| `default` (fallback) | $0.000015 | $0.000075 |

### Baseline Cost (Without Nexus)

Every request hits the most expensive model (Opus) at full, unpruned token count:

```
baseline = Σ (original_tokens × opus_input_price + completion_tokens × opus_output_price)
           for ALL requests
```

Where `completion_tokens = response_size // 4`.

### Optimized Cost (With Nexus)

Only cache-MISS requests incur API cost, at pruned token counts and routed model pricing:

```
optimized = Σ (pruned_tokens × model_input_price + completion_tokens × model_output_price)
            for MISS requests only (HITs cost $0)
```

Where `pruned_tokens = original_tokens - tokens_saved`.

### Savings Breakdown by Source

Three distinct savings categories for the narrative:

1. **Cache savings** = baseline cost of all HIT requests (they cost $0 with Nexus)
2. **Pruning savings** = Σ (tokens_saved × per-token price) for MISS requests
3. **Routing savings** = Σ ((opus_input - sonnet_input) × pruned_tokens + (opus_output - sonnet_output) × completion_tokens) for MISS requests routed to Sonnet

## HTML Dashboard Layout

Self-contained HTML with inline CSS and inline JS. No external dependencies, no CDN, no build step.

### Visual Design

- Dark navy/charcoal background (`#0f1117`)
- Glassmorphism cards with subtle gradient borders
- CSS `conic-gradient` for donut charts, `width: X%` divs for bar charts
- CSS `@keyframes` count-up animation on hero numbers
- CSS Grid responsive layout
- Inter/system font stack

### Panel Layout (3 rows × 2 columns)

#### Row 1: Hero Metrics (3 cards)
- **Cost Reduction**: `$X.XX → $Y.YY` with `-ZZ.Z%` badge (green)
- **Tokens Saved**: `XXX,XXX → YY,YYY` with percentage badge (cyan)
- **API Calls Avoided**: `N → M` with cache-hit count (purple)

#### Row 2: Optimization Breakdown (2 cards)
- **Cache Performance**: Donut chart (HIT/MISS/BYPASS distribution) + average latency per cache status
- **Routing Distribution**: Horizontal bar chart (Opus / Sonnet / Other percentages)

#### Row 3: Detail Panels (2 cards)
- **Pruning Impact**: Bar chart per transform type (whitespace, comments, dedup, truncation) showing token contribution
- **Latency Profile**: P50/P95/P99 bar chart with min/max values

### Data Injection

Simple Python string template replacement — no Jinja2:

```python
html = HTML_TEMPLATE.replace("{{COST_BASELINE}}", f"{cost_baseline:.2f}")
html = html.replace("{{COST_OPTIMIZED}}", f"{cost_optimized:.2f}")
# ... etc
```

## CLI Interface

### Usage

```bash
python scratch/benchmark_cli.py [OPTIONS]
```

### Arguments

| Flag | Default | Description |
|---|---|---|
| `--url` | `http://localhost:8000/v1/chat/completions` | Gateway endpoint URL |
| `--dataset` | `scratch/dummy_requests.jsonl` | Path to JSONL dataset |
| `--requests` | `50` | Number of requests to send |
| `--concurrency` | `5` | Concurrent request limit |
| `--model` | `auto` | Model to request (use `auto` to test routing) |
| `--stream` | `false` | Enable streaming mode (reports TTFT) |
| `--output` | `scratch/benchmark_report.html` | Output HTML file path |
| `--no-open` | `false` | Skip auto-opening browser |

### Terminal Output

Progress bar during execution:

```
⚡ Nexus Benchmark CLI — running 50 requests (concurrency=5)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[██████████████████░░░░░░░░░░░░] 36/50  Cache: 12 HIT, 24 MISS
```

Completion summary:

```
✅ Benchmark complete — 50 requests in 12.4s
📊 Report saved to scratch/benchmark_report.html
🌐 Opening in browser...
```

## Error Handling

| Scenario | Behavior |
|---|---|
| Gateway unreachable | Fail fast: `"Cannot reach gateway at {url}. Is it running?"` |
| All requests fail | Generate report with error metrics highlighted in red |
| Missing response headers | Default to 0 / empty — report shows "N/A" for that section |
| Dataset file not found | Exit with `"Dataset not found at {path}. Run data_collector.py first."` |
| Output file write fails | Print error, dump JSON summary to stdout as fallback |

## How to Demo

### Prerequisites

```bash
# 1. Start infrastructure
docker compose up -d

# 2. Start mock upstream (terminal 1)
python scratch/mock_upstream.py

# 3. Start gateway (terminal 2)
export UPSTREAM_API_URL=http://127.0.0.1:8001/v1/chat/completions
export UPSTREAM_API_KEY=mock-key-123
python -m src
```

### Run the Benchmark

```bash
# Generate the ROI scorecard
python scratch/benchmark_cli.py --requests 50 --model auto

# The HTML report auto-opens in your browser
```

### Interview Talking Points

From the generated dashboard, highlight:

1. **Cost reduction**: "The gateway reduced API spend by ~67% through three layers of optimization"
2. **Cache hit rate**: "Repeated queries are served in <10ms from the semantic cache, eliminating the API call entirely"
3. **Routing intelligence**: "Simple tasks are automatically routed to Sonnet ($3/M) instead of Opus ($15/M) — a 5x price reduction"
4. **Pruning efficiency**: "Deterministic transforms strip ~20-40% of tokens before they reach the API, with <5ms overhead"
