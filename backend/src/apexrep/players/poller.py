import logging
import time

import asyncpg
from pydantic import BaseModel

from apexrep.als.errors import AlsError, PlayerNotFound, RateLimited
from apexrep.als.rate_limiter import Clock
from apexrep.config import Settings
from apexrep.db import Pool
from apexrep.players import repo
from apexrep.players.matches import MatchKind
from apexrep.players.service import AlsGateway

logger = logging.getLogger("apexrep.poller")


class PollSummary(BaseModel):
    expired: int = 0
    raw_cleared: int = 0
    polled: int = 0
    changed: int = 0
    matches: int = 0
    untracked_not_found: int = 0
    errors: int = 0
    rate_limited: bool = False
    # True when the whole run was skipped because a rate-limit backoff is in force.
    backing_off: bool = False


class Poller:
    """One pass over the tracked players that are due for a poll."""

    def __init__(
        self,
        *,
        pool: Pool,
        als: AlsGateway,
        settings: Settings,
        clock: Clock = time.monotonic,
    ) -> None:
        self._pool: Pool = pool
        self._als: AlsGateway = als
        self._settings: Settings = settings
        self._clock: Clock = clock
        self._backoff_s: float = 0.0
        self._resume_at: float = 0.0
        # Due immediately, so the cleanup also runs once at worker start.
        self._next_maintenance_at: float = clock()

    async def run_once(self) -> PollSummary:
        settings = self._settings
        summary = PollSummary()
        summary.expired = await repo.expire_tracking(
            self._pool, max_idle_s=settings.tracking_expiry_s
        )
        if self._clock() >= self._next_maintenance_at:
            # Scheduled before it runs and contained if it fails, so a broken cleanup
            # can never stop the polling below.
            self._next_maintenance_at = self._clock() + settings.worker_maintenance_interval_s
            try:
                summary.raw_cleared = await repo.clear_old_raw(
                    self._pool, max_age_s=settings.raw_retention_s
                )
            except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
                logger.exception("raw retention cleanup failed")

        if self._clock() < self._resume_at:
            summary.backing_off = True
            return summary

        due = await repo.fetch_due_players(self._pool, limit=settings.worker_batch_limit)
        for player in due:
            try:
                snapshot = await self._als.bridge_by_uid(player.uid, player.platform)
            except RateLimited:
                self._back_off()
                summary.rate_limited = True
                break
            except PlayerNotFound:
                untracked = await repo.record_not_found(
                    self._pool,
                    player.uid,
                    player.platform,
                    limit=settings.worker_not_found_limit,
                    retry_after_s=settings.worker_poll_active_s,
                )
                if untracked:
                    summary.untracked_not_found += 1
                    logger.warning(
                        "untracked %s:%s after repeated 404s", player.platform, player.uid
                    )
                continue
            except AlsError:
                logger.exception("poll failed for %s:%s", player.platform, player.uid)
                summary.errors += 1
                await repo.defer_poll(
                    self._pool, player.uid, player.platform, delay_s=settings.worker_poll_active_s
                )
                continue

            result = await repo.store_snapshot(
                self._pool, snapshot, session_gap_s=settings.session_gap_s
            )
            await repo.schedule_next_poll(
                self._pool,
                player.uid,
                player.platform,
                changed=result.changed,
                active_s=settings.worker_poll_active_s,
                idle_s=settings.worker_poll_idle_s,
                idle_after_unchanged=settings.worker_idle_after_unchanged,
            )
            summary.polled += 1
            summary.changed += int(result.changed)
            summary.matches += int(result.match is MatchKind.MATCH)
        else:
            self._backoff_s = 0.0
        return summary

    def _back_off(self) -> None:
        settings = self._settings
        self._backoff_s = min(
            settings.worker_rate_limit_backoff_max_s,
            self._backoff_s * 2 if self._backoff_s else settings.worker_rate_limit_backoff_s,
        )
        self._resume_at = self._clock() + self._backoff_s
        logger.warning("rate limited by ALS, pausing polls for %ss", self._backoff_s)
