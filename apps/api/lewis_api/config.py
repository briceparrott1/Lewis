from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ROOT_ENV, extra="ignore")

    database_url: str = (
        "postgresql+asyncpg://lewis:lewis_local_dev@localhost:5432/lewis"
    )
    jwt_secret: str = "change-me-in-prod"
    jwt_expire_days: int = 7
    max_results: int = 6
    cookie_secure: bool = False
    anthropic_api_key: str = ""
    agent_model: str = "claude-haiku-4-5-20251001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
