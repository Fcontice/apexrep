import json
from datetime import datetime

import asyncpg
from pydantic import BaseModel

from apexrep.als.models import Platform, PlayerSnapshot
from apexrep.db import Pool
from apexrep.players.matches import MatchKind, detect_match

# Serialises track requests so the tracked-player cap cannot be overshot.
_TRACKING_LOCK_KEY: int = 4_150_001


class TrackingFull(Exception):
    """The tracked-player cap is reached and nobody is idle enough to evict."""


class StoredSnapshot(BaseModel):
    taken_at: datetime
    level: int
    level_prestige: int
    level_progress: int
    rank_name: str | None
    rank_div: int | None
    rank_score: int | None
    selected_legend: str | None
    trackers: dict[str, int]


class StoredPlayer(BaseModel):
    uid: str
    platform: Platform
    current_name: str
    is_tracked: bool
    tracked_since: datetime | None
    last_polled_at: datetime | None
    polled_age_s: float | None
    snapshot: StoredSnapshot | None


class StoredAlias(BaseModel):
    uid: str
    current_name: str


class StoreResult(BaseModel):
    # True when the poll differed from the latest snapshot and a row was inserted.
    changed: bool
    match: MatchKind | None


class DuePlayer(BaseModel):
    uid: str
    platform: Platform


def _snapshot_from_row(row: asyncpg.Record) -> StoredSnapshot | None:
    if row["snapshot_id"] is None:
        return None
    return StoredSnapshot(
        taken_at=row["taken_at"],
        level=row["level"],
        level_prestige=row["level_prestige"],
        level_progress=row["level_progress"],
        rank_name=row["rank_name"],
        rank_div=row["rank_div"],
        rank_score=row["rank_score"],
        selected_legend=row["selected_legend"],
        trackers=json.loads(row["trackers"]),
    )


async def fetch_player(pool: Pool, uid: str, platform: Platform) -> StoredPlayer | None:
    """The player with their latest snapshot, or None if the player is unknown."""
    row = await pool.fetchrow(
        """
        select p.uid, p.platform, p.current_name, p.is_tracked, p.tracked_since,
               p.last_polled_at,
               extract(epoch from now() - p.last_polled_at)::float8 as polled_age_s,
               s.id as snapshot_id, s.taken_at, s.level, s.level_prestige, s.level_progress,
               s.rank_name, s.rank_div, s.rank_score, s.selected_legend, s.trackers
        from players p
        left join lateral (
          select * from snapshots
          where uid = p.uid and platform = p.platform
          order by taken_at desc, id desc
          limit 1
        ) s on true
        where p.uid = $1 and p.platform = $2
        """,
        uid,
        platform.value,
    )
    if row is None:
        return None
    return StoredPlayer(
        uid=row["uid"],
        platform=Platform(row["platform"]),
        current_name=row["current_name"],
        is_tracked=row["is_tracked"],
        tracked_since=row["tracked_since"],
        last_polled_at=row["last_polled_at"],
        polled_age_s=row["polled_age_s"],
        snapshot=_snapshot_from_row(row),
    )


def _comparable(snapshot: PlayerSnapshot | StoredSnapshot) -> tuple[object, ...]:
    return (
        snapshot.level,
        snapshot.level_prestige,
        snapshot.level_progress,
        snapshot.rank_name,
        snapshot.rank_div,
        snapshot.rank_score,
        snapshot.selected_legend,
        snapshot.trackers,
    )


async def store_snapshot(
    pool: Pool, snapshot: PlayerSnapshot, *, session_gap_s: float
) -> StoreResult:
    """Record a successful poll, from the worker or a page load.

    Inserts a snapshot row only if something changed, and a match row if the
    change looks like play.
    """
    uid, platform = snapshot.uid, snapshot.platform.value
    async with pool.acquire() as conn, conn.transaction():
        # Transaction-scoped so it also works through a transaction-mode pooler.
        await conn.execute(
            "select pg_advisory_xact_lock(hashtextextended($1, 0))", f"{platform}:{uid}"
        )
        before = await conn.fetchrow(
            """
            select is_tracked,
                   extract(epoch from now() - last_polled_at)::float8 as gap_s
            from players
            where uid = $1 and platform = $2
            """,
            uid,
            platform,
        )
        await conn.execute(
            """
            insert into players (uid, platform, current_name, last_polled_at)
            values ($1, $2, $3, now())
            on conflict (uid, platform) do update
              set current_name = excluded.current_name,
                  last_polled_at = excluded.last_polled_at,
                  not_found_count = 0
            """,
            uid,
            platform,
            snapshot.name,
        )
        latest_row = await conn.fetchrow(
            """
            select id as snapshot_id, taken_at, level, level_prestige, level_progress,
                   rank_name, rank_div, rank_score, selected_legend, trackers
            from snapshots
            where uid = $1 and platform = $2
            order by taken_at desc, id desc
            limit 1
            """,
            uid,
            platform,
        )
        latest = _snapshot_from_row(latest_row) if latest_row is not None else None
        if latest is not None and _comparable(latest) == _comparable(snapshot):
            return StoreResult(changed=False, match=None)

        new_id: int = await conn.fetchval(
            """
            insert into snapshots (
              uid, platform, level, level_prestige, level_progress,
              rank_name, rank_div, rank_score, selected_legend, trackers, raw
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb)
            returning id
            """,
            uid,
            platform,
            snapshot.level,
            snapshot.level_prestige,
            snapshot.level_progress,
            snapshot.rank_name,
            snapshot.rank_div,
            snapshot.rank_score,
            snapshot.selected_legend,
            json.dumps(snapshot.trackers),
            json.dumps(snapshot.raw),
        )
        if latest is None or latest_row is None or before is None:
            return StoreResult(changed=True, match=None)

        draft = detect_match(
            latest,
            snapshot,
            gap_s=before["gap_s"],
            session_gap_s=session_gap_s,
            # A gap marker only means something on a continuously polled player.
            record_gaps=before["is_tracked"],
        )
        if draft is None:
            return StoreResult(changed=True, match=None)

        await conn.execute(
            """
            insert into matches (
              uid, platform, kind, detected_at, prev_snapshot_id, next_snapshot_id,
              legend, level_progress_delta, rank_score_delta, tracker_deltas
            )
            values ($1, $2, $3, now(), $4, $5, $6, $7, $8, $9::jsonb)
            """,
            uid,
            platform,
            draft.kind.value,
            latest_row["snapshot_id"],
            new_id,
            draft.legend,
            draft.level_progress_delta,
            draft.rank_score_delta,
            json.dumps(draft.tracker_deltas),
        )
        return StoreResult(changed=True, match=draft.kind)


async def touch_viewed(pool: Pool, uid: str, platform: Platform) -> None:
    await pool.execute(
        "update players set last_viewed_at = now() where uid = $1 and platform = $2",
        uid,
        platform.value,
    )


async def fetch_fresh_alias(
    pool: Pool, platform: Platform, name_lower: str, *, max_age_s: float
) -> StoredAlias | None:
    row = await pool.fetchrow(
        """
        select a.uid, p.current_name
        from player_aliases a
        join players p on p.uid = a.uid and p.platform = a.platform
        where a.platform = $1
          and a.name_lower = $2
          and a.resolved_at > now() - make_interval(secs => $3::float8)
        """,
        platform.value,
        name_lower,
        max_age_s,
    )
    if row is None:
        return None
    return StoredAlias(uid=row["uid"], current_name=row["current_name"])


async def upsert_alias(pool: Pool, platform: Platform, name_lower: str, uid: str) -> None:
    await pool.execute(
        """
        insert into player_aliases (platform, name_lower, uid)
        values ($1, $2, $3)
        on conflict (platform, name_lower) do update
          set uid = excluded.uid, resolved_at = now()
        """,
        platform.value,
        name_lower,
        uid,
    )


# --- tracking ----------------------------------------------------------------


async def track_player(
    pool: Pool, uid: str, platform: Platform, *, cap: int, evict_min_idle_s: float
) -> datetime | None:
    """Start tracking a known player. Returns tracked_since, or None if unknown.

    Idempotent. At the cap, evicts the least recently viewed tracked player if it
    has been idle for `evict_min_idle_s`; otherwise raises TrackingFull.
    """
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("select pg_advisory_xact_lock($1)", _TRACKING_LOCK_KEY)
        row = await conn.fetchrow(
            "select is_tracked, tracked_since from players where uid = $1 and platform = $2",
            uid,
            platform.value,
        )
        if row is None:
            return None
        if row["is_tracked"]:
            await conn.execute(
                "update players set last_viewed_at = now() where uid = $1 and platform = $2",
                uid,
                platform.value,
            )
            already_since: datetime = row["tracked_since"]
            return already_since

        tracked_count: int = await conn.fetchval("select count(*) from players where is_tracked")
        if tracked_count >= cap:
            evicted = await conn.fetchval(
                """
                update players set is_tracked = false, next_poll_at = null
                where (uid, platform) = (
                  select uid, platform from players
                  where is_tracked
                    and coalesce(last_viewed_at, tracked_since)
                        < now() - make_interval(secs => $1::float8)
                  order by coalesce(last_viewed_at, tracked_since) asc
                  limit 1
                )
                returning uid
                """,
                evict_min_idle_s,
            )
            if evicted is None:
                raise TrackingFull

        tracked_since: datetime = await conn.fetchval(
            """
            update players
            set is_tracked = true, tracked_since = now(), next_poll_at = now(),
                unchanged_polls = 0, not_found_count = 0, last_viewed_at = now()
            where uid = $1 and platform = $2
            returning tracked_since
            """,
            uid,
            platform.value,
        )
        return tracked_since


async def expire_tracking(pool: Pool, *, max_idle_s: float) -> int:
    """Untrack players nobody has viewed for `max_idle_s`. Returns how many."""
    rows = await pool.fetch(
        """
        update players set is_tracked = false, next_poll_at = null
        where is_tracked
          and coalesce(last_viewed_at, tracked_since) < now() - make_interval(secs => $1::float8)
        returning uid
        """,
        max_idle_s,
    )
    return len(rows)


async def fetch_due_players(pool: Pool, *, limit: int) -> list[DuePlayer]:
    rows = await pool.fetch(
        """
        select uid, platform from players
        where is_tracked and (next_poll_at is null or next_poll_at <= now())
        order by next_poll_at asc nulls first
        limit $1
        """,
        limit,
    )
    return [DuePlayer(uid=row["uid"], platform=Platform(row["platform"])) for row in rows]


async def schedule_next_poll(
    pool: Pool,
    uid: str,
    platform: Platform,
    *,
    changed: bool,
    active_s: float,
    idle_s: float,
    idle_after_unchanged: int,
) -> None:
    await pool.execute(
        """
        update players
        set unchanged_polls = case when $3 then 0 else unchanged_polls + 1 end,
            next_poll_at = now() + make_interval(secs =>
              case when $3 or unchanged_polls + 1 < $6 then $4::float8 else $5::float8 end)
        where uid = $1 and platform = $2
        """,
        uid,
        platform.value,
        changed,
        active_s,
        idle_s,
        idle_after_unchanged,
    )


async def defer_poll(pool: Pool, uid: str, platform: Platform, *, delay_s: float) -> None:
    await pool.execute(
        """
        update players set next_poll_at = now() + make_interval(secs => $3::float8)
        where uid = $1 and platform = $2
        """,
        uid,
        platform.value,
        delay_s,
    )


async def record_not_found(
    pool: Pool, uid: str, platform: Platform, *, limit: int, retry_after_s: float
) -> bool:
    """Count a 404 for a tracked player. Returns True if that untracked them."""
    still_tracked: bool | None = await pool.fetchval(
        """
        update players
        set not_found_count = not_found_count + 1,
            is_tracked = is_tracked and not_found_count + 1 < $3,
            next_poll_at = now() + make_interval(secs => $4::float8)
        where uid = $1 and platform = $2
        returning is_tracked
        """,
        uid,
        platform.value,
        limit,
        retry_after_s,
    )
    return still_tracked is False
