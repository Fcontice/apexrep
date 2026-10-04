import json

import pytest

from apexrep.als.errors import PlayerNotFound, RateLimited, UpstreamError
from apexrep.als.models import Platform
from apexrep.config import Settings
from apexrep.db import Pool
from apexrep.players import repo
from apexrep.players.matches import MatchKind
from apexrep.players.poller import Poller
from apexrep.players.repo import TrackingFull
from apexrep.players.service import PlayerService
from tests.fakes import FIXTURE_UID, FakeAls, FakeClock

pytestmark = pytest.mark.anyio

UID: str = FIXTURE_UID
OTHER_UID: str = "222"


def make_settings(*, tracked_players_cap: int = 200) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql://unused",
        tracked_players_cap=tracked_players_cap,
    )


@pytest.fixture
def als() -> FakeAls:
    return FakeAls()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def service(pool: Pool, als: FakeAls, settings: Settings) -> PlayerService:
    return PlayerService(pool=pool, als=als, settings=settings)


@pytest.fixture
def poller(pool: Pool, als: FakeAls, settings: Settings, clock: FakeClock) -> Poller:
    return Poller(pool=pool, als=als, settings=settings, clock=clock)


async def tracked_player(service: PlayerService, als: FakeAls) -> None:
    """Resolve and track the fixture player, then forget the calls that took."""
    await service.resolve(Platform.PC, "xXfrankX")
    await service.track(Platform.PC, UID)
    als.by_uid_calls = 0


async def make_due(pool: Pool) -> None:
    await pool.execute("update players set next_poll_at = now() - interval '1 second'")


async def player_field(pool: Pool, expression: str, uid: str = UID) -> object:
    return await pool.fetchval(f"select {expression} from players where uid = $1", uid)


async def seconds_until_next_poll(pool: Pool) -> float:
    seconds = await player_field(pool, "extract(epoch from next_poll_at - now())::float8")
    assert isinstance(seconds, float)
    return seconds


def play(als: FakeAls, *, progress: int = 3, kills: int = 2) -> None:
    """Change the fake's snapshot the way a played match would."""
    trackers = dict(als.snapshot.trackers)
    trackers["career_kills"] += kills
    als.snapshot = als.snapshot.model_copy(
        update={"level_progress": als.snapshot.level_progress + progress, "trackers": trackers}
    )


# --- track -------------------------------------------------------------------


async def test_track_marks_the_player_tracked_and_due(
    service: PlayerService, als: FakeAls, pool: Pool
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    tracked_since = await service.track(Platform.PC, UID)

    assert await player_field(pool, "is_tracked") is True
    assert await player_field(pool, "tracked_since") == tracked_since
    assert await player_field(pool, "next_poll_at <= now()") is True
    assert await player_field(pool, "last_viewed_at is not null") is True


async def test_track_is_idempotent(service: PlayerService, als: FakeAls) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    first = await service.track(Platform.PC, UID)
    second = await service.track(Platform.PC, UID)
    assert first == second


async def test_track_unknown_player_is_not_found(service: PlayerService) -> None:
    with pytest.raises(PlayerNotFound):
        await service.track(Platform.PC, "999")


async def test_track_at_the_cap_is_refused_until_someone_is_idle_enough_to_evict(
    pool: Pool, als: FakeAls
) -> None:
    service = PlayerService(pool=pool, als=als, settings=make_settings(tracked_players_cap=1))
    await service.resolve(Platform.PC, "xXfrankX")
    await service.get_profile(Platform.PC, OTHER_UID, is_crawler=False)
    await service.track(Platform.PC, UID)

    with pytest.raises(TrackingFull):
        await service.track(Platform.PC, OTHER_UID)
    assert await player_field(pool, "is_tracked", OTHER_UID) is False

    await pool.execute(
        "update players set last_viewed_at = now() - interval '2 days' where uid = $1", UID
    )
    await service.track(Platform.PC, OTHER_UID)
    assert await player_field(pool, "is_tracked", OTHER_UID) is True
    assert await player_field(pool, "is_tracked", UID) is False


# --- poller ------------------------------------------------------------------


async def test_untracked_players_are_not_polled(
    service: PlayerService, poller: Poller, als: FakeAls
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    summary = await poller.run_once()

    assert summary.polled == 0
    assert als.by_uid_calls == 0


async def test_due_tracked_player_is_polled_and_rescheduled(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    summary = await poller.run_once()

    assert summary.polled == 1
    assert summary.changed == 0
    assert als.by_uid_calls == 1
    assert 200 < await seconds_until_next_poll(pool) <= 240

    again = await poller.run_once()
    assert again.polled == 0
    assert als.by_uid_calls == 1


async def test_progress_between_polls_records_a_match(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    await poller.run_once()
    await make_due(pool)
    play(als, progress=3, kills=2)

    summary = await poller.run_once()
    assert summary.changed == 1
    assert summary.matches == 1

    row = await pool.fetchrow("select * from matches")
    assert row is not None
    assert row["kind"] == "match"
    assert row["legend"] == "Octane"
    assert row["level_progress_delta"] == 3
    assert row["rank_score_delta"] == 0
    assert json.loads(row["tracker_deltas"]) == {"career_kills": 2}
    assert row["prev_snapshot_id"] != row["next_snapshot_id"]


async def test_progress_after_a_long_gap_records_a_session_gap(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    await poller.run_once()
    await make_due(pool)
    await pool.execute("update players set last_polled_at = now() - interval '1 hour'")
    play(als)

    summary = await poller.run_once()
    assert summary.changed == 1
    assert summary.matches == 0
    assert await pool.fetchval("select kind from matches") == "session_gap"


async def test_untracked_player_gets_no_session_gap_row(
    service: PlayerService, als: FakeAls, pool: Pool, settings: Settings
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    await pool.execute("update players set last_polled_at = now() - interval '1 hour'")
    play(als)

    result = await repo.store_snapshot(pool, als.snapshot, session_gap_s=settings.session_gap_s)
    assert result.changed is True
    assert result.match is None
    assert await pool.fetchval("select count(*) from matches") == 0


async def test_page_load_soon_after_a_poll_records_a_match_even_if_untracked(
    service: PlayerService, als: FakeAls, pool: Pool, settings: Settings
) -> None:
    await service.resolve(Platform.PC, "xXfrankX")
    play(als)

    result = await repo.store_snapshot(pool, als.snapshot, session_gap_s=settings.session_gap_s)
    assert result.match is MatchKind.MATCH


async def test_unchanged_polls_back_off_to_the_idle_interval_and_a_change_resets_it(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    for _ in range(4):
        await poller.run_once()
        await make_due(pool)
    assert await player_field(pool, "unchanged_polls") == 4

    await poller.run_once()
    assert await player_field(pool, "unchanged_polls") == 5
    assert 860 < await seconds_until_next_poll(pool) <= 900

    await make_due(pool)
    play(als)
    await poller.run_once()
    assert await player_field(pool, "unchanged_polls") == 0
    assert 200 < await seconds_until_next_poll(pool) <= 240


async def test_repeated_404s_untrack_the_player(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    als.errors_by_uid[UID] = PlayerNotFound("gone")

    for _ in range(2):
        summary = await poller.run_once()
        assert summary.untracked_not_found == 0
        assert await player_field(pool, "is_tracked") is True
        await make_due(pool)

    summary = await poller.run_once()
    assert summary.untracked_not_found == 1
    assert await player_field(pool, "is_tracked") is False


async def test_a_successful_poll_resets_the_404_count(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    als.errors_by_uid[UID] = PlayerNotFound("blip")
    await poller.run_once()
    assert await player_field(pool, "not_found_count") == 1

    del als.errors_by_uid[UID]
    await make_due(pool)
    await poller.run_once()
    assert await player_field(pool, "not_found_count") == 0


async def test_rate_limit_stops_the_batch_and_pauses_polling(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool, clock: FakeClock
) -> None:
    await tracked_player(service, als)
    await service.get_profile(Platform.PC, OTHER_UID, is_crawler=False)
    await service.track(Platform.PC, OTHER_UID)
    als.by_uid_calls = 0
    als.errors_by_uid = {UID: RateLimited("slow down"), OTHER_UID: RateLimited("slow down")}

    summary = await poller.run_once()
    assert summary.rate_limited is True
    assert summary.polled == 0
    assert als.by_uid_calls == 1

    paused = await poller.run_once()
    assert paused.backing_off is True
    assert als.by_uid_calls == 1

    als.errors_by_uid = {}
    clock.now += 31.0
    resumed = await poller.run_once()
    assert resumed.backing_off is False
    assert resumed.polled == 2


async def test_upstream_error_defers_the_player_and_keeps_tracking(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    als.errors_by_uid[UID] = UpstreamError("down")

    summary = await poller.run_once()
    assert summary.errors == 1
    assert await player_field(pool, "is_tracked") is True
    assert 200 < await seconds_until_next_poll(pool) <= 240


async def test_tracking_expires_without_a_recent_view(
    service: PlayerService, poller: Poller, als: FakeAls, pool: Pool
) -> None:
    await tracked_player(service, als)
    await pool.execute("update players set last_viewed_at = now() - interval '15 days'")

    summary = await poller.run_once()
    assert summary.expired == 1
    assert summary.polled == 0
    assert await player_field(pool, "is_tracked") is False
