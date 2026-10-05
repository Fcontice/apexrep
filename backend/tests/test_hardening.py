import asyncpg
import pytest

from apexrep.als.models import Platform
from apexrep.api.ip_limit import IpRateLimiter
from apexrep.config import Settings
from apexrep.db import Pool, asyncpg_dsn
from apexrep.players import repo
from apexrep.players.poller import Poller
from apexrep.players.service import PlayerService
from tests.fakes import FakeAls, FakeClock

# --- per-IP limiter ----------------------------------------------------------


def test_requests_within_the_limit_pass_and_the_next_is_refused() -> None:
    clock = FakeClock()
    limiter = IpRateLimiter(limit=2, window_s=60.0, clock=clock)

    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") == pytest.approx(60.0)


def test_retry_after_counts_down_and_the_window_resets() -> None:
    clock = FakeClock()
    limiter = IpRateLimiter(limit=1, window_s=60.0, clock=clock)
    limiter.check("a")

    clock.now += 45.0
    assert limiter.check("a") == pytest.approx(15.0)

    clock.now += 15.0
    assert limiter.check("a") is None


def test_ips_are_counted_separately() -> None:
    limiter = IpRateLimiter(limit=1, window_s=60.0, clock=FakeClock())
    assert limiter.check("a") is None
    assert limiter.check("b") is None
    assert limiter.check("a") is not None


def test_refused_requests_do_not_extend_the_window() -> None:
    clock = FakeClock()
    limiter = IpRateLimiter(limit=1, window_s=60.0, clock=clock)
    limiter.check("a")
    for _ in range(5):
        clock.now += 10.0
        limiter.check("a")

    clock.now += 10.0
    assert limiter.check("a") is None


def test_memory_stays_bounded_when_every_window_is_still_live() -> None:
    clock = FakeClock()
    limiter = IpRateLimiter(limit=5, window_s=60.0, clock=clock, max_ips=3)
    for index in range(10):
        clock.now += 1.0
        assert limiter.check(f"ip-{index}") is None
    assert len(limiter._windows) == 3


# --- connection string -------------------------------------------------------


def test_neon_connection_string_loses_the_parameter_asyncpg_rejects() -> None:
    neon = (
        "postgresql://user:pw@ep-x-pooler.us-east-2.aws.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )
    assert asyncpg_dsn(neon) == (
        "postgresql://user:pw@ep-x-pooler.us-east-2.aws.neon.tech/db?sslmode=require"
    )


def test_plain_connection_string_is_unchanged() -> None:
    local = "postgresql://apexrep:apexrep@localhost:5433/apexrep"
    assert asyncpg_dsn(local) == local


# --- raw retention -----------------------------------------------------------

anyio = pytest.mark.anyio


async def _add_snapshot(pool: Pool, *, days_ago: int) -> None:
    await pool.execute(
        """
        insert into snapshots (uid, platform, taken_at, level, level_progress, raw)
        values ('1', 'PC', now() - make_interval(days => $1), 10, 5, '{"k": 1}')
        """,
        days_ago,
    )


@anyio
async def test_old_raw_responses_are_cleared_and_recent_ones_kept(pool: Pool) -> None:
    await pool.execute("insert into players (uid, platform, current_name) values ('1','PC','P')")
    await _add_snapshot(pool, days_ago=31)
    await _add_snapshot(pool, days_ago=29)

    cleared = await repo.clear_old_raw(pool, max_age_s=30 * 86_400.0)

    assert cleared == 1
    assert await pool.fetchval("select count(*) from snapshots where raw is not null") == 1
    # The snapshot itself stays; only its raw copy goes.
    assert await pool.fetchval("select count(*) from snapshots") == 2
    assert await repo.clear_old_raw(pool, max_age_s=30 * 86_400.0) == 0


@anyio
async def test_worker_runs_the_cleanup_at_start_and_then_on_its_interval(pool: Pool) -> None:
    await pool.execute("insert into players (uid, platform, current_name) values ('1','PC','P')")
    clock = FakeClock()
    settings = Settings(_env_file=None, database_url="postgresql://unused")
    poller = Poller(pool=pool, als=FakeAls(), settings=settings, clock=clock)

    await _add_snapshot(pool, days_ago=31)
    assert (await poller.run_once()).raw_cleared == 1

    await _add_snapshot(pool, days_ago=31)
    assert (await poller.run_once()).raw_cleared == 0

    clock.now += 3601.0
    assert (await poller.run_once()).raw_cleared == 1


@anyio
async def test_a_failing_cleanup_does_not_stop_polling(
    pool: Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken_cleanup(pool: Pool, *, max_age_s: float) -> int:
        raise asyncpg.QueryCanceledError("statement timeout")

    monkeypatch.setattr(repo, "clear_old_raw", broken_cleanup)
    als = FakeAls()
    settings = Settings(_env_file=None, database_url="postgresql://unused")
    service = PlayerService(pool=pool, als=als, settings=settings)
    await service.resolve(Platform.PC, "xXfrankX")
    await service.track(Platform.PC, als.snapshot.uid)
    poller = Poller(pool=pool, als=als, settings=settings, clock=FakeClock())

    summary = await poller.run_once()
    assert summary.raw_cleared == 0
    assert summary.polled == 1
