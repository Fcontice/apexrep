"""Insert a made-up player with three days of history, for looking at the charts
and the matches table locally: `uv run apexrep-seed-demo`.

Development only. Re-running replaces the demo player's rows.
"""

import asyncio
import json
import random
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from apexrep.config import Settings, get_settings
from apexrep.db import Connection, connect

LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", "db"})
DEMO_UID: str = "9000000000001"
DEMO_PLATFORM: str = "PC"
DEMO_NAME: str = "DemoPlayer"
SESSIONS: int = 6
MATCHES_PER_SESSION: int = 11


async def seed(conn: Connection) -> int:
    rng = random.Random(7)
    now = datetime.now(UTC)

    async with conn.transaction():
        for table in ("matches", "snapshots", "player_aliases", "players"):
            await conn.execute(
                f"delete from {table} where uid = $1 and platform = $2", DEMO_UID, DEMO_PLATFORM
            )
        await conn.execute(
            """
            insert into players (uid, platform, current_name, last_polled_at)
            values ($1, $2, $3, now())
            """,
            DEMO_UID,
            DEMO_PLATFORM,
            DEMO_NAME,
        )
        await conn.execute(
            "insert into player_aliases (platform, name_lower, uid) values ($1, $2, $3)",
            DEMO_PLATFORM,
            DEMO_NAME.lower(),
            DEMO_UID,
        )

        level, progress, rank_score = 212, 35, 9400
        kills, damage = 4310, 1_210_000
        previous_id: int | None = None
        match_count = 0

        for session in range(SESSIONS):
            # Two evening sessions a day, oldest first, the last one ending recently.
            session_start = now - timedelta(hours=12 * (SESSIONS - session) - 2)
            legend = "Wraith" if session % 3 == 2 else "Octane"
            for index in range(MATCHES_PER_SESSION + 1):
                taken_at = session_start + timedelta(minutes=18 * index)
                first_of_session = index == 0
                if not first_of_session:
                    gained_progress = rng.randint(2, 9)
                    progress += gained_progress
                    if progress >= 100:
                        progress -= 100
                        level += 1
                    rank_delta = rng.choice([-45, -30, -20, 15, 30, 55, 80, 120])
                    rank_score += rank_delta
                    gained_kills = rng.randint(0, 9)
                    gained_damage = rng.randint(150, 2400)
                    kills += gained_kills
                    damage += gained_damage

                trackers = {"kills": kills, "damage": damage}
                snapshot_id: int = await conn.fetchval(
                    """
                    insert into snapshots (uid, platform, taken_at, level, level_prestige,
                                           level_progress, rank_name, rank_div, rank_score,
                                           selected_legend, trackers)
                    values ($1, $2, $3, $4, 0, $5, 'Platinum', 3, $6, $7, $8::jsonb)
                    returning id
                    """,
                    DEMO_UID,
                    DEMO_PLATFORM,
                    taken_at,
                    level,
                    progress,
                    rank_score,
                    legend,
                    json.dumps(trackers),
                )
                if previous_id is not None:
                    is_gap = first_of_session
                    await conn.execute(
                        """
                        insert into matches (uid, platform, kind, detected_at,
                                             prev_snapshot_id, next_snapshot_id, legend,
                                             level_progress_delta, rank_score_delta,
                                             tracker_deltas)
                        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                        """,
                        DEMO_UID,
                        DEMO_PLATFORM,
                        "session_gap" if is_gap else "match",
                        taken_at,
                        previous_id,
                        snapshot_id,
                        None if is_gap else legend,
                        None if is_gap else gained_progress,
                        None if is_gap else rank_delta,
                        json.dumps(
                            {}
                            if is_gap
                            else {
                                key: value
                                for key, value in (
                                    ("kills", gained_kills),
                                    ("damage", gained_damage),
                                )
                                if value > 0
                            }
                        ),
                    )
                    match_count += 1
                previous_id = snapshot_id
    return match_count


def _require_local_database(database_url: str) -> None:
    host = urlsplit(database_url).hostname
    if host not in LOCAL_HOSTS:
        raise SystemExit(f"refusing to seed demo data into a non-local database ({host})")


async def run(settings: Settings) -> None:
    _require_local_database(settings.database_url)
    conn = await connect(settings)
    try:
        match_count = await seed(conn)
    finally:
        await conn.close()
    print(f"seeded {DEMO_NAME}: {match_count} match rows -> /player/pc/{DEMO_UID}")


def main() -> None:
    asyncio.run(run(get_settings()))


if __name__ == "__main__":
    main()
