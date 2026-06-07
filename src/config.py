from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Upstream LLM API configuration
    upstream_api_url: str = "https://api.openai.com/v1/chat/completions"
    upstream_api_key: str = ""
    upstream_timeout: float = 120.0  # seconds

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Semantic caching
    cache_enabled: bool = True
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 3600  # seconds (1 hour)
    cache_similarity_threshold: float = 0.95
    cache_max_response_bytes: int = 524288  # 512 KB

    # Dynamic routing
    routing_enabled: bool = True
    routing_trigger_model: str = "auto"
    routing_token_threshold: int = 2000
    routing_low_model: str = "claude-sonnet-4-20250514"
    routing_high_model: str = "claude-opus-4-0520"
    # Comma-separated list of high-complexity keywords (whole-word matched)
    routing_complexity_keywords: str = (
        "refactor,architect,design,optimize,analyze,debug,review,explain"
    )


# Module-level singleton — imported by other modules
settings = Settings()
