from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT: Path = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_url: str
    als_api_key: SecretStr = SecretStr("")
    internal_token: SecretStr = SecretStr("")
    migrations_dir: Path = REPO_ROOT / "migrations"

    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    worker_loop_interval_s: float = 30.0
    worker_heartbeat_stale_s: float = 90.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
