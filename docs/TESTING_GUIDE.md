# Semantic Caching: Manual Testing Guide

This guide provides step-by-step instructions to manually verify the semantic caching implementation before archiving the change.

## Prerequisites

1.  **OrbStack (or Docker)**: Required to run Redis with the RediSearch module (Redis Stack).
2.  **Python Virtual Environment**: You must activate your virtual environment in any terminal you use before running Python commands:
    ```bash
    source venv/bin/activate
    ```
3.  **cURL**: For making HTTP requests to the gateway.

## 1. Environment Setup

### 1.1 Start Redis Stack
Semantic caching requires the RediSearch module. Start a Redis Stack container locally using the provided `docker-compose.yml`:
```bash
docker compose up -d
```

### 1.2 Upstream Provider & .env Configuration
The gateway needs an upstream LLM to forward cache misses to. You can either use a real OpenAI API key, or use the provided local mock server.

Ensure your `.env` file at the root of the project contains the following:

**Option A: Using the Local Mock Server (No API Key Required)**
```env
CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379

UPSTREAM_API_URL=http://localhost:8001/v1/chat/completions
UPSTREAM_API_KEY=mock-key-123
```

**Option B: Using OpenAI Directly**
```env
CACHE_ENABLED=true
REDIS_URL=redis://localhost:6379

UPSTREAM_API_URL=https://api.openai.com/v1/chat/completions
UPSTREAM_API_KEY=sk-your-actual-api-key-goes-here
```

### 1.3 Start the Services

You will need **two separate terminals** if you are using the mock server. Remember to run `source venv/bin/activate` in both!

**Terminal 1: Start the Mock Server (Skip if using Option B)**
```bash
python mock_upstream.py
```

**Terminal 2: Start the Gateway**
```bash
python -m src
```
*Wait for the server to start. You should see logs indicating the embedding engine (`all-MiniLM-L6-v2`) is loading and the RediSearch index is being created.*

---

## 2. Testing Scenarios

*Run these commands from a third terminal (or just a new tab).*

### Scenario 1: Cache Miss (First Request)
Send a prompt to the gateway. This should result in a cache MISS.

```bash
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_tenant" \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain quantum computing in one simple sentence."}
    ]
  }'
```
**Verification:**
*   Check the response headers. You should see `X-Cache: MISS`.
*   If using the mock server, you will see a printout in Terminal 1 indicating it received the request.
*   The response time will be normal (e.g., 1-3 seconds, depending on the upstream API).

### Scenario 2: Cache Hit (Identical Prompt)
Send the exact same request again immediately.

```bash
# Run the exact same curl command from Scenario 1
```
**Verification:**
*   Check the response headers. You should see `X-Cache: HIT`.
*   If using the mock server, Terminal 1 will **not** show any new activity (because the request never reached it).
*   The response should appear almost instantly (near-zero latency).
*   The content should perfectly match the first response.

### Scenario 3: Cache Hit (Temperature Bucketing)
Our system currently does exact context hashing to prevent false positives in multi-turn chats, but the embedding search happens first. For this test, try a slightly modified temperature to ensure bucketing works (e.g. 0.70 vs 0.74).

```bash
# First, send with temperature 0.70
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_tenant" \
  -d '{
    "model": "gpt-4o",
    "temperature": 0.70,
    "messages": [
      {"role": "user", "content": "What is the capital of Japan?"}
    ]
  }'

# Then, send with temperature 0.74 (should round to same bucket: 7)
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_tenant" \
  -d '{
    "model": "gpt-4o",
    "temperature": 0.74,
    "messages": [
      {"role": "user", "content": "What is the capital of Japan?"}
    ]
  }'
```
**Verification:**
*   The second request should return `X-Cache: HIT`.

### Scenario 4: Tenant Isolation
Ensure a cache entry for one tenant cannot be accessed by another.

```bash
# Send request as Tenant A (use Scenario 1 prompt)
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tenantA_secret" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Tell me a joke about a tomato."}]
  }'
# Should be X-Cache: MISS

# Send SAME request as Tenant B
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer tenantB_secret" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Tell me a joke about a tomato."}]
  }'
```
**Verification:**
*   The request for `tenantB` MUST return `X-Cache: MISS`.

### Scenario 5: Cache Bypass
Test that the cache can be bypassed via configuration.

1.  Stop the gateway server (Terminal 2).
2.  Set `CACHE_ENABLED=false` in your `.env`.
3.  Restart the gateway server: `python -m src`

```bash
# Send any request
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_tenant" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```
**Verification:**
*   The response header should explicitly state `X-Cache: BYPASS`.

### Scenario 6: Graceful Degradation (Redis Down)
Test that the gateway continues to serve traffic if Redis fails.

1.  Stop the Redis container: `docker compose stop`
2.  Ensure `CACHE_ENABLED=true` is set in your `.env`.
3.  Restart the gateway server: `python -m src`
4.  *Note: You should see a warning in the logs during startup that Redis could not connect and caching is disabled.*

```bash
# Send a request
curl -i -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test_tenant" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Are you working?"}]
  }'
```
**Verification:**
*   The request should succeed (Status 200 OK).
*   The response header should state `X-Cache: MISS`.
*   The application should not crash.

---

## 3. Cleanup
Once testing is complete, you can remove the Redis container and its volumes, and stop your mock server:
```bash
docker compose down -v
```
