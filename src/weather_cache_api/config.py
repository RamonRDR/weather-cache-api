"""Environment-based configuration."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = Field(default=600, ge=1, le=86400)
    http_timeout_seconds: float = Field(default=5.0, gt=0, le=60)
