# Nexus - Token Optimization Engine (PRD)

As enterprise adoption of Large Language Models (LLMs) accelerates, API costs and inference latency are scaling quadratically. Current Retrieval-Augmented Generation (RAG) and coding assistant pipelines suffer from massive token bloat due to the ingestion of raw, unoptimized files, redundant system instructions, and a lack of request caching. There is a critical need for a centralized, multi-layered optimization engine that intelligently compresses context, caches redundant queries, and deterministically parses codebases to drastically reduce token spend while improving Time-to-First-Token (TTFT).

## Architecture

Nexus is an **OpenAI-compatible proxy**. Clients (VS Code, Cursor, Antigravity, agents) set `OPENAI_BASE_URL=http://localhost:8000` and Nexus transparently intercepts, optimizes, and forwards requests to the configured upstream provider (any OpenAI-compatible API — OpenAI, Azure OpenAI, Anthropic via proxy, etc.).

## Core Features & Architectural Layers

### Layer 1: Context Interception & Gateway (The Proxy)

- **OpenAI-Compatible API:** Exposes `POST /v1/chat/completions` with full support for both `stream: true` (SSE) and `stream: false` responses. Drop-in replacement — zero client changes required.
- **Tenant-Aware Semantic Caching:** Intercepts outgoing LLM requests and embeds the last user message using a local, lightweight model (`all-MiniLM-L6-v2`). Queries a Redis vector database (scoped by tenant ID, system prompt hash, model, temperature bucket, and conversation context hash) to find semantically identical historical requests (cosine similarity > 0.92), serving cached responses instantly and bypassing the LLM API entirely.
- **Dynamic Model Routing:** Automatically routes simpler tasks to cheaper, faster models (Sonnet) while reserving flagship models (Opus) for complex reasoning, using a heuristic classifier (token count + keyword signals) to stay within the latency budget.
- **Fault Tolerance:** If the semantic cache or any optimization layer fails, the gateway gracefully falls back to a direct, unoptimized API pass-through to prevent blocking developer workflows.

### Layer 2: Pre-Flight Prompt Pruning

- **Rule-Based Token Stripping:** Applies fast, deterministic transformations to reduce token count without ML inference:
    - Whitespace normalization (collapse multiple newlines, trailing spaces)
    - Code comment stripping from embedded source blocks
    - Duplicate system instruction deduplication in multi-turn conversations
    - Token-budget-aware conversation truncation (keep system + last N turns)
- **Expected savings: 20-40%** at < 5ms latency cost.

### Layer 3: Deterministic Codebase Parsing (AST & Graphify) — Future

- **Tree-sitter AST Extraction:** Replaces the expensive practice of dumping entire raw source code files into the context window. Instead, deterministic parsers extract only the relevant function signatures, class definitions, and import trees.
- **Local Knowledge Graphs (Graphify):** Maps the extracted AST data into a queryable graph structure on disk. The LLM queries this graph to understand code dependencies and architecture, spending zero tokens on raw file orientation.

### Layer 4: Real-Time Telemetry & Observability

- **In-Flight Metrics Interception:** Implements an asynchronous FastAPI middleware layer to intercept every inbound and outbound payload to measure gateway performance without blocking the core execution thread.
- **Prometheus Integration:** Exposes an internal `/metrics` scrape endpoint to track business ROI and operational health in real-time. The core metrics tracked include:
    - **Latency Delta:** Measures total turnaround time, tracking the system's ability to maintain a sub-50ms response on cache hits versus raw cloud inference.
    - **Token Cost Reduction & Volume Saved:** Accumulates the total number of tokens stripped via pruning or bypassed via Redis caching.
    - **Routing Distribution Ratio:** Tracks the percentage of traffic successfully offloaded to Sonnet versus Opus.
    - **Proxy Overhead Latency:** Monitors gateway internal execution time to guarantee the proxy introduces less than 15-20ms of processing latency on a cache miss.

## Technical Requirements

- **Core Gateway:** Python with **FastAPI** to handle highly concurrent, async HTTP requests with minimal overhead.
- **State & Caching:** **Redis** (with RediSearch/Vector similarity search enabled) to handle Semantic Caching.
- **Local ML Infrastructure:** HuggingFace `sentence-transformers` for local embeddings (`all-MiniLM-L6-v2`).
- **Token Counting:** `tiktoken` for fast, CPU-based token estimation.
- **Code Parsing (Future):** `Tree-sitter` bindings for multi-language syntax tree generation.
- **Observability Stack:** `prometheus_client` instrumentation.
- **Deployment:** Docker Compose (Redis + Nexus) for local development.

## Non-Technical Requirements

- **Ultra-Low Overhead Latency:** The gateway proxy, cache lookup, and routing logic must execute in under 50 milliseconds to ensure developers do not experience network drag.
- **Strict Multi-Tenant Data Isolation:** Cached responses from one tenant must never be accessible or exposed to another tenant. All vector cache lookups must be strictly scoped by an authorized Tenant ID.
- **Fault Tolerance:** If the semantic cache or pruning engine fails, the gateway must gracefully fall back to a direct, unoptimized API pass-through to prevent blocking developer workflows.
