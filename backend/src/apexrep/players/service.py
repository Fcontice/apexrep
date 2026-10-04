import asyncio
import time
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel

from apexrep.als.errors import AlsError, PlayerNotFound
from apexrep.als.models import Platform, PlayerSnapshot
from apexrep.als.rate_limiter import Clock
from apexrep.config import Settings
from apexrep.db import Pool
from apexrep.players import repo
from apexrep.players.repo import StoredPlayer, StoredSnapshot

NEGATIVE_CACHE_MAX_ENTRIES: int = 2000


class AlsGateway(Protocol):
    async def bridge_by_uid(self, uid: str, platform: Platform) -> PlayerSnapshot: ...

    async def bridge_by_name(self, name: str, platform: Platform) -> PlayerSnapshot: ...

    def backlog_s(self) -> float: ...


class ProfileUnavailable(Exception):
    """ALS could not be reached and there is no stored snapshot to fall back on."""


class ResolvedPlayer(BaseModel):
    uid: str
    platform: Platform
    name: str


class ProfileResult(BaseModel):
    player: StoredPlayer
    snapshot: StoredSnapshot
    # True when the data is older than the freshness window and could not be refreshed.
    stale: bool


def normalize_name(name: str) -> str:
    return name.strip().lower()


class PlayerService:
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
        self._refreshes: dict[tuple[str, Platform], asyncio.Task[None]] = {}
        self._not_found_until: dict[tuple[Platform, str], float] = {}

    async def resolve(self, platform: Platform, name: str) -> ResolvedPlayer:
        name_lower = normalize_name(name)
        if not name_lower:
            raise PlayerNotFound("empty player name")

        alias = await repo.fetch_fresh_alias(
            self._pool, platform, name_lower, max_age_s=self._settings.alias_ttl_s
        )
        if alias is not None:
            return ResolvedPlayer(uid=alias.uid, platform=platform, name=alias.current_name)

        cache_key = (platform, name_lower)
        if self._not_found_until.get(cache_key, 0.0) > self._clock():
            raise PlayerNotFound(f"{name_lower!r} was not found recently")

        try:
            snapshot = await self._als.bridge_by_name(name.strip(), platform)
        except PlayerNotFound:
            self._remember_not_found(cache_key)
            raise

        await repo.store_snapshot(self._pool, snapshot, session_gap_s=self._settings.session_gap_s)
        # The alias is the name the visitor typed, which ALS just resolved. The name
        # in the response is display-only: for Steam players ALS cannot look it up.
        await repo.upsert_alias(self._pool, platform, name_lower, snapshot.uid)
        return ResolvedPlayer(uid=snapshot.uid, platform=platform, name=snapshot.name)

    async def get_profile(self, platform: Platform, uid: str, *, is_crawler: bool) -> ProfileResult:
        player = await repo.fetch_player(self._pool, uid, platform)

        # Crawlers only ever get stored data: no ALS call, no view recorded.
        if not is_crawler and self._needs_refresh(player):
            has_snapshot = player is not None and player.snapshot is not None
            budget_free = self._als.backlog_s() <= self._settings.als_max_refresh_wait_s
            # With nothing stored there is nothing to fall back on, so wait for the budget.
            if budget_free or not has_snapshot:
                try:
                    await self._refresh(uid, platform)
                except PlayerNotFound:
                    if not has_snapshot:
                        raise
                except AlsError as exc:
                    if not has_snapshot:
                        raise ProfileUnavailable(str(exc)) from exc
                player = await repo.fetch_player(self._pool, uid, platform)

        if player is None or player.snapshot is None:
            raise PlayerNotFound(f"no stored data for {platform.value}:{uid}")
        if not is_crawler:
            await repo.touch_viewed(self._pool, uid, platform)
        return ProfileResult(
            player=player, snapshot=player.snapshot, stale=self._needs_refresh(player)
        )

    async def track(self, platform: Platform, uid: str) -> datetime:
        """Start tracking a player the site already knows. Returns tracked_since."""
        tracked_since = await repo.track_player(
            self._pool,
            uid,
            platform,
            cap=self._settings.tracked_players_cap,
            evict_min_idle_s=self._settings.tracking_evict_min_idle_s,
        )
        if tracked_since is None:
            raise PlayerNotFound(f"cannot track unknown player {platform.value}:{uid}")
        return tracked_since

    def _needs_refresh(self, player: StoredPlayer | None) -> bool:
        if player is None or player.snapshot is None or player.polled_age_s is None:
            return True
        return player.polled_age_s > self._settings.profile_max_age_s

    async def _refresh(self, uid: str, platform: Platform) -> None:
        """Single-flight: concurrent loads of one profile share one ALS call."""
        key = (uid, platform)
        task = self._refreshes.get(key)
        if task is None:
            task = asyncio.create_task(self._ingest_snapshot(uid, platform))
            self._refreshes[key] = task
            task.add_done_callback(lambda _: self._refreshes.pop(key, None))
        # Shielded so one cancelled request does not cancel the shared call.
        await asyncio.shield(task)

    async def _ingest_snapshot(self, uid: str, platform: Platform) -> None:
        snapshot = await self._als.bridge_by_uid(uid, platform)
        await repo.store_snapshot(self._pool, snapshot, session_gap_s=self._settings.session_gap_s)

    def _remember_not_found(self, cache_key: tuple[Platform, str]) -> None:
        now = self._clock()
        if len(self._not_found_until) >= NEGATIVE_CACHE_MAX_ENTRIES:
            self._not_found_until = {
                key: until for key, until in self._not_found_until.items() if until > now
            }
        self._not_found_until[cache_key] = now + self._settings.resolve_not_found_ttl_s
