"""Semantic caching package for the Nexus Token-Optimization Gateway.

This package provides:
- EmbeddingEngine: local all-MiniLM-L6-v2 sentence embeddings
- CacheKeyBuilder: composite cache key construction from request metadata
- RedisCacheStore: Redis + RediSearch vector store for cached responses
- CacheLookup: orchestrates embed → search → verify flow
- StreamBuffer: transparent SSE stream interception for cache population
- CacheReplay: synthetic SSE/JSON re-streaming from cache on HIT
"""
