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

    als_base_url: str = "https://api.apexlegendsstatus.com"
    als_timeout_s: float = 10.0
    als_max_retries: int = 2
    als_retry_backoff_s: float = 1.0
    # The 5 requests/second ALS limit is split between the two processes.
    als_rate_backend_per_s: float = 1.5
    als_rate_worker_per_s: float = 3.0

    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    worker_loop_interval_s: float = 30.0
    worker_heartbeat_stale_s: float = 90.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
