from prometheus_client import Counter, Histogram, Gauge

# Cache hits and misses counters
cache_hits_total = Counter(
    "cache_hits_total",
    "Total number of semantic cache hits",
    ["model"]
)

cache_misses_total = Counter(
    "cache_misses_total",
    "Total number of semantic cache misses",
    ["model"]
)

# Tokens saved counter
tokens_saved_total = Counter(
    "tokens_saved_total",
    "Total number of tokens saved",
    ["model", "source"]
)

# Cost saved counter (in USD)
cost_saved_dollars_total = Counter(
    "cost_saved_dollars_total",
    "Total cost saved in USD",
    ["model", "source"]
)

# Prices in USD per token (derived from $3/$15 per M for Sonnet, $15/$75 per M for Opus)
MODEL_PRICES = {
    "claude-sonnet-4-20250514": {"input": 0.000003, "output": 0.000015},
    "claude-opus-4-0520": {"input": 0.000015, "output": 0.000075},
    "default": {"input": 0.000015, "output": 0.000075}
}

# Total tokens processed counter
tokens_processed_total = Counter(
    "tokens_processed_total",
    "Total number of tokens processed before optimization",
    ["model"]
)

# Latency histograms
gateway_latency_seconds = Histogram(
    "gateway_latency_seconds",
    "Total latency of the gateway in seconds",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

provider_latency_seconds = Histogram(
    "provider_latency_seconds",
    "Latency of the upstream provider in seconds",
    ["provider", "model"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
)

# Routing distribution gauge
requests_per_model = Gauge(
    "requests_per_model",
    "Active requests per model",
    ["model"]
)

# AST Extraction & Query Observability Metrics
ast_queries_total = Counter(
    "ast_queries_total",
    "Total number of AST subgraph queries",
    ["status"]
)

ast_query_latency_seconds = Histogram(
    "ast_query_latency_seconds",
    "Latency of AST subgraph queries in seconds",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

ast_extractions_total = Counter(
    "ast_extractions_total",
    "Total number of AST file extractions",
    ["language", "status"]
)

ast_extraction_latency_seconds = Histogram(
    "ast_extraction_latency_seconds",
    "Latency of AST file extractions in seconds",
    ["language"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

