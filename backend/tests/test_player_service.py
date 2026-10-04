import asyncio

import pytest

from apexrep.als.errors import PlayerNotFound, UpstreamError
from apexrep.als.models import Platform
from apexrep.config import Settings
from apexrep.db import Pool
from apexrep.players.service import PlayerService, ProfileUnavailable
from tests.fakes import FIXTURE_UID, FakeAls, FakeClock

pytestmark = pytest.mark.anyio

UID: str = FIXTURE_UID


@pytest.fixture
def als() -> FakeAls:
    return FakeAls()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def service(pool: Pool, als: FakeAls, clock: FakeClock) -> PlayerService:
    settings = Settings(database_url="postgresql://unused")
    return PlayerService(pool=pool, als=als, settings=settings, clock=clock)


async def age_last_poll(pool: Pool, seconds: int) -> None:
    await pool.execute(
        "update players set last_polled_at = now() - make_interval(secs => $1::float8)",
        float(seconds),
    )


async def snapshot_count(pool: Pool) -> int:
    count: int = await pool.fetchval("select count(*) from snapshots")
    return count


# --- resolve ---------------------------------------------------------------


async def test_resolve_stores_player_alias_and_first_snapshot(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    resolved = await service.resolve(Platform.PC, "  xXfrankX ")

    assert resolved.uid == UID
    assert resolved.name == "vinyasaflowTTV"
    assert als.by_name_calls == 1
    assert await snapshot_count(pool) == 1
    # The alias is what the visitor typed, not the display name ALS returned.
    aliases = await pool.fetch("select name_lower, uid from player_aliases")
    assert [(row["name_lower"], row["uid"]) for row in aliases] == [("xxfrankx", UID)]


async def test_resolve_uses_cached_alias_case_insensitively(
    service: PlayerService, als: FakeAls
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    again = await service.resolve(Platform.PC, "XXFRANKX")

    assert again.uid == UID
    assert als.by_name_calls == 1


async def test_resolve_calls_als_again_once_the_alias_expires(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await pool.execute("update player_aliases set resolved_at = now() - interval '25 hours'")
    await service.resolve(Platform.PC, "xXfrankX")

    assert als.by_name_calls == 2


async def test_resolve_remembers_not_found_for_the_ttl(
    service: PlayerService, als: FakeAls, clock: FakeClock
) -> None:
    als.error = PlayerNotFound("nope")
    with pytest.raises(PlayerNotFound):
        await service.resolve(Platform.PC, "nobody")
    with pytest.raises(PlayerNotFound):
        await service.resolve(Platform.PC, "Nobody")
    assert als.by_name_calls == 1

    clock.now += 301.0
    with pytest.raises(PlayerNotFound):
        await service.resolve(Platform.PC, "nobody")
    assert als.by_name_calls == 2


async def test_resolve_does_not_cache_upstream_failures(
    service: PlayerService, als: FakeAls
) -> None:
    als.error = UpstreamError("down")
    with pytest.raises(UpstreamError):
        await service.resolve(Platform.PC, "xXfrankX")
    als.error = None
    resolved = await service.resolve(Platform.PC, "xXfrankX")
    assert resolved.uid == UID


# --- profile ---------------------------------------------------------------


async def test_profile_right_after_resolve_makes_no_als_call(
    service: PlayerService, als: FakeAls
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    result = await service.get_profile(Platform.PC, UID, is_crawler=False)

    assert als.by_uid_calls == 0
    assert result.stale is False
    assert result.snapshot.level == 382
    assert result.snapshot.trackers["career_kills"] == 12988


async def test_stale_profile_is_refreshed_once_and_unchanged_data_adds_no_snapshot(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)

    result = await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert als.by_uid_calls == 1
    assert result.stale is False
    assert await snapshot_count(pool) == 1

    await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert als.by_uid_calls == 1


async def test_changed_data_adds_a_snapshot(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)
    als.snapshot = als.snapshot.model_copy(update={"level_progress": 14})

    result = await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert result.snapshot.level_progress == 14
    assert await snapshot_count(pool) == 2


async def test_simultaneous_loads_of_a_stale_profile_make_one_als_call(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)
    als.delay_s = 0.05

    results = await asyncio.gather(
        *(service.get_profile(Platform.PC, UID, is_crawler=False) for _ in range(5))
    )
    assert als.by_uid_calls == 1
    assert all(result.stale is False for result in results)


async def test_als_failure_serves_the_stored_snapshot_marked_stale(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)
    als.error = UpstreamError("down")

    result = await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert result.stale is True
    assert result.snapshot.level == 382


async def test_used_up_als_budget_serves_the_stored_snapshot_without_calling(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)
    als.backlog = 30.0

    result = await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert als.by_uid_calls == 0
    assert result.stale is True


async def test_crawler_gets_stored_data_without_als_call_or_view(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await age_last_poll(pool, 600)

    result = await service.get_profile(Platform.PC, UID, is_crawler=True)
    assert als.by_uid_calls == 0
    assert result.snapshot.level == 382
    assert await pool.fetchval("select last_viewed_at from players") is None


async def test_visitor_view_is_recorded(service: PlayerService, pool: Pool) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert await pool.fetchval("select last_viewed_at from players") is not None


async def test_unknown_uid_is_fetched_from_als(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    result = await service.get_profile(Platform.PC, UID, is_crawler=False)
    assert als.by_uid_calls == 1
    assert result.player.current_name == "vinyasaflowTTV"
    assert await snapshot_count(pool) == 1


async def test_unknown_uid_not_found_in_als_is_player_not_found(
    service: PlayerService, als: FakeAls
) -> None:
    als.error = PlayerNotFound("nope")
    with pytest.raises(PlayerNotFound):
        await service.get_profile(Platform.PC, "999", is_crawler=False)


async def test_unknown_uid_with_als_down_is_profile_unavailable(
    service: PlayerService, als: FakeAls
) -> None:
    als.error = UpstreamError("down")
    with pytest.raises(ProfileUnavailable):
        await service.get_profile(Platform.PC, "999", is_crawler=False)


async def test_crawler_on_unknown_uid_is_not_found_without_als_call(
    service: PlayerService, als: FakeAls
) -> None:
    with pytest.raises(PlayerNotFound):
        await service.get_profile(Platform.PC, "999", is_crawler=True)
    assert als.by_uid_calls == 0
