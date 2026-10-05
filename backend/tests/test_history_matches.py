from datetime import UTC, datetime

import pytest

from apexrep.als.models import Platform
from apexrep.api.cursor import InvalidCursor, decode_cursor, encode_cursor
from apexrep.config import Settings
from apexrep.db import Pool
from apexrep.players.matches import MatchKind
from apexrep.players.repo import MatchCursor
from apexrep.players.service import PlayerService
from tests.fakes import FIXTURE_UID, FakeAls

pytestmark = pytest.mark.anyio

UID: str = FIXTURE_UID


def make_service(pool: Pool, *, history_max_points: int = 2000) -> PlayerService:
    settings = Settings(
        _env_file=None, database_url="postgresql://unused", history_max_points=history_max_points
    )
    return PlayerService(pool=pool, als=FakeAls(), settings=settings)


async def seed_player(pool: Pool) -> None:
    await pool.execute(
        "insert into players (uid, platform, current_name) values ($1, 'PC', 'Seeded')", UID
    )


async def add_snapshot(pool: Pool, *, hours_ago: float, progress: int, kills: int) -> int:
    snapshot_id: int = await pool.fetchval(
        """
        insert into snapshots (uid, platform, taken_at, level, level_prestige, level_progress,
                               rank_score, trackers)
        values ($1, 'PC', now() - make_interval(secs => $2::float8), 100, 1, $3, 5000,
                jsonb_build_object('kills', $4::int))
        returning id
        """,
        UID,
        hours_ago * 3600,
        progress,
        kills,
    )
    return snapshot_id


async def add_match(pool: Pool, prev_id: int, next_id: int, *, minutes_ago: float) -> None:
    await pool.execute(
        """
        insert into matches (uid, platform, kind, detected_at, prev_snapshot_id,
                             next_snapshot_id, legend, level_progress_delta, rank_score_delta,
                             tracker_deltas)
        values ($1, 'PC', 'match', now() - make_interval(secs => $2::float8), $3, $4,
                'Octane', 2, 10, '{"kills": 1}')
        """,
        UID,
        minutes_ago * 60,
        prev_id,
        next_id,
    )


# --- history -----------------------------------------------------------------


async def test_history_is_oldest_first_and_limited_to_the_window(pool: Pool) -> None:
    await seed_player(pool)
    await add_snapshot(pool, hours_ago=1, progress=30, kills=12)
    await add_snapshot(pool, hours_ago=30, progress=20, kills=10)
    await add_snapshot(pool, hours_ago=24 * 40, progress=10, kills=1)

    history = await make_service(pool).get_history(Platform.PC, UID, days=30)

    assert history.bucketed is False
    assert [point.level_progress for point in history.points] == [20, 30]
    assert history.points[1].trackers == {"kills": 12}
    assert history.points[1].rank_score == 5000


async def test_history_days_are_capped_at_the_configured_maximum(pool: Pool) -> None:
    await seed_player(pool)
    await add_snapshot(pool, hours_ago=24 * 100, progress=10, kills=1)
    await add_snapshot(pool, hours_ago=24 * 80, progress=20, kills=2)

    history = await make_service(pool).get_history(Platform.PC, UID, days=365)
    assert [point.level_progress for point in history.points] == [20]


async def test_long_history_is_reduced_to_the_last_snapshot_of_each_hour(pool: Pool) -> None:
    await seed_player(pool)
    # Offsets are measured from the top of the current hour so the buckets are stable.
    for minutes_into_hour, hours_back, progress in [(10, 2, 1), (40, 2, 2), (10, 1, 3), (40, 1, 4)]:
        await pool.execute(
            """
            insert into snapshots (uid, platform, taken_at, level, level_prestige,
                                   level_progress, trackers)
            values ($1, 'PC',
                    date_trunc('hour', now()) - make_interval(hours => $2)
                      + make_interval(mins => $3),
                    100, 1, $4, '{}')
            """,
            UID,
            hours_back,
            minutes_into_hour,
            progress,
        )

    history = await make_service(pool, history_max_points=3).get_history(Platform.PC, UID, days=30)

    assert history.bucketed is True
    assert [point.level_progress for point in history.points] == [2, 4]


async def test_history_of_an_unknown_player_is_empty(pool: Pool) -> None:
    history = await make_service(pool).get_history(Platform.PC, "999", days=30)
    assert history.points == []


# --- matches -----------------------------------------------------------------


async def test_matches_are_newest_first_and_paginate_without_gaps_or_repeats(pool: Pool) -> None:
    await seed_player(pool)
    first = await add_snapshot(pool, hours_ago=10, progress=1, kills=1)
    second = await add_snapshot(pool, hours_ago=9, progress=2, kills=2)
    for index in range(5):
        # Each match needs its own snapshot pair; the pair is unique.
        extra = await add_snapshot(pool, hours_ago=8 - index, progress=3 + index, kills=3 + index)
        await add_match(pool, first if index == 0 else second, extra, minutes_ago=50 - index * 10)
    service = make_service(pool)

    page_one = await service.get_matches(Platform.PC, UID, limit=2, before=None)
    assert len(page_one.items) == 2
    assert page_one.next_cursor is not None

    page_two = await service.get_matches(Platform.PC, UID, limit=2, before=page_one.next_cursor)
    page_three = await service.get_matches(Platform.PC, UID, limit=2, before=page_two.next_cursor)
    assert len(page_two.items) == 2
    assert len(page_three.items) == 1
    assert page_three.next_cursor is None

    seen = [item.id for page in (page_one, page_two, page_three) for item in page.items]
    assert len(set(seen)) == 5
    times = [item.detected_at for page in (page_one, page_two, page_three) for item in page.items]
    assert times == sorted(times, reverse=True)
    assert page_one.items[0].kind is MatchKind.MATCH
    assert page_one.items[0].tracker_deltas == {"kills": 1}


async def test_a_full_last_page_has_no_next_cursor(pool: Pool) -> None:
    await seed_player(pool)
    first = await add_snapshot(pool, hours_ago=3, progress=1, kills=1)
    second = await add_snapshot(pool, hours_ago=2, progress=2, kills=2)
    await add_match(pool, first, second, minutes_ago=5)

    page = await make_service(pool).get_matches(Platform.PC, UID, limit=1, before=None)
    assert len(page.items) == 1
    assert page.next_cursor is None


# --- cursor ------------------------------------------------------------------


def test_cursor_round_trips() -> None:
    cursor = MatchCursor(detected_at=datetime(2026, 10, 4, 12, 30, 15, 123456, tzinfo=UTC), id=42)
    assert decode_cursor(encode_cursor(cursor)) == cursor


@pytest.mark.parametrize("value", ["", "not-base64!!", "aGVsbG8=", "e30="])
def test_bad_cursors_are_rejected(value: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(value)
