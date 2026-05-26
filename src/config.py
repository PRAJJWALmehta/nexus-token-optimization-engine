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


# Module-level singleton — imported by other modules
settings = Settings()
