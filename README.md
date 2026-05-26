# Nexus Token-Optimization Gateway

A transparent, OpenAI-compatible reverse-proxy gateway that sits between LLM clients and upstream AI APIs. Phase 1 establishes the foundational pass-through scaffold — subsequent phases will layer in caching, prompt pruning, and intelligent routing.

## Architecture

```
Client → POST /v1/chat/completions → [Nexus Gateway] → Upstream LLM API
```

## Getting Started

```bash
# Install dependencies
pip install -e .

# Configure upstream
export UPSTREAM_API_URL=https://api.openai.com/v1/chat/completions
export UPSTREAM_API_KEY=sk-...

# Run the gateway
python -m src
```

The gateway will start on `http://localhost:8000`. Point any OpenAI-compatible client at it.
