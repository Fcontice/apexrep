from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import SecretStr, model_validator
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

    # A profile is refreshed from ALS when its last poll is older than this.
    profile_max_age_s: float = 300.0
    # A profile refresh is skipped (cached data is served) if it would wait longer than this.
    als_max_refresh_wait_s: float = 2.0
    alias_ttl_s: float = 86_400.0
    resolve_not_found_ttl_s: float = 300.0

    db_pool_min_size: int = 1
    db_pool_max_size: int = 5

    worker_loop_interval_s: float = 30.0
    worker_heartbeat_stale_s: float = 90.0
    worker_batch_limit: int = 200
    # Poll every `active` seconds; after `idle_after` unchanged polls in a row, every `idle`.
    worker_poll_active_s: float = 240.0
    worker_poll_idle_s: float = 900.0
    worker_idle_after_unchanged: int = 5
    worker_not_found_limit: int = 3
    worker_rate_limit_backoff_s: float = 30.0
    worker_rate_limit_backoff_max_s: float = 600.0

    # Progress seen after a longer gap between polls is a session gap, not a match.
    session_gap_s: float = 1800.0

    tracked_players_cap: int = 200
    tracking_expiry_s: float = 14 * 86_400.0
    # When the cap is full, a tracked player unviewed for this long can be evicted.
    tracking_evict_min_idle_s: float = 86_400.0

    @model_validator(mode="after")
    def _idle_poll_stays_inside_gap_window(self) -> Self:
        if self.worker_poll_idle_s >= self.session_gap_s:
            raise ValueError("worker_poll_idle_s must be below session_gap_s")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
