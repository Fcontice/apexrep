import asyncio
from datetime import UTC, datetime

import pytest

from apexrep.als.errors import UpstreamError
from apexrep.als.models import MapRotation, Platform, PredatorThreshold
from apexrep.als.parser import parse_map_rotation, parse_predator
from apexrep.config import Settings
from apexrep.meta import MetaService
from tests.conftest import load_fixture
from tests.fakes import FakeClock

pytestmark = pytest.mark.anyio


class FakeMetaAls:
    def __init__(self) -> None:
        self.rotation: MapRotation = parse_map_rotation(load_fixture("maprotation_ok.json"))
        self.thresholds: dict[Platform, PredatorThreshold] = parse_predator(
            load_fixture("predator_ok.json")
        )
        self.error: UpstreamError | None = None
        self.delay_s: float = 0.0
        self.rotation_calls: int = 0
        self.predator_calls: int = 0

    async def map_rotation(self) -> MapRotation:
        self.rotation_calls += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.error is not None:
            raise self.error
        return self.rotation

    async def predator(self) -> dict[Platform, PredatorThreshold]:
        self.predator_calls += 1
        if self.error is not None:
            raise self.error
        return self.thresholds


@pytest.fixture
def als() -> FakeMetaAls:
    return FakeMetaAls()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def meta(als: FakeMetaAls, clock: FakeClock) -> MetaService:
    settings = Settings(_env_file=None, database_url="postgresql://unused")
    return MetaService(als=als, settings=settings, clock=clock)


# --- parsers, against recorded responses -----------------------------------


def test_parse_map_rotation_from_recorded_response() -> None:
    rotation = parse_map_rotation(load_fixture("maprotation_ok.json"))

    assert rotation.battle_royale is not None
    assert rotation.battle_royale.current.map == "Broken Moon"
    assert rotation.battle_royale.current.end == datetime(2026, 10, 5, 0, 30, tzinfo=UTC)
    assert rotation.battle_royale.next is not None
    assert rotation.battle_royale.next.map == "World's Edge"
    assert rotation.ranked is not None
    assert rotation.ranked.current.map == "World's Edge"


def test_parse_predator_from_recorded_response_drops_switch() -> None:
    thresholds = parse_predator(load_fixture("predator_ok.json"))

    assert set(thresholds) == {Platform.PC, Platform.PS4, Platform.X1}
    assert thresholds[Platform.PC].rank_score == 24798
    assert thresholds[Platform.PC].masters_and_preds == 6179
    assert thresholds[Platform.X1].rank_score == 17334


def test_unexpected_shapes_are_upstream_errors() -> None:
    with pytest.raises(UpstreamError):
        parse_map_rotation({"battle_royale": {"current": {"map": "no times"}}})
    with pytest.raises(UpstreamError):
        parse_predator({"nope": 1})


# --- caching -----------------------------------------------------------------


async def test_map_rotation_is_cached_for_its_ttl(
    meta: MetaService, als: FakeMetaAls, clock: FakeClock
) -> None:
    await meta.map_rotation()
    await meta.map_rotation()
    assert als.rotation_calls == 1

    clock.now += 61.0
    await meta.map_rotation()
    assert als.rotation_calls == 2


async def test_predator_has_its_own_longer_ttl(
    meta: MetaService, als: FakeMetaAls, clock: FakeClock
) -> None:
    await meta.predator()
    clock.now += 61.0
    await meta.predator()
    assert als.predator_calls == 1

    clock.now += 900.0
    await meta.predator()
    assert als.predator_calls == 2


async def test_concurrent_requests_share_one_fetch(meta: MetaService, als: FakeMetaAls) -> None:
    als.delay_s = 0.05
    await asyncio.gather(*(meta.map_rotation() for _ in range(5)))
    assert als.rotation_calls == 1


async def test_failed_refresh_serves_the_previous_value(
    meta: MetaService, als: FakeMetaAls, clock: FakeClock
) -> None:
    first = await meta.map_rotation()
    clock.now += 61.0
    als.error = UpstreamError("down")

    assert await meta.map_rotation() == first


async def test_an_outage_costs_one_upstream_attempt_per_retry_interval(
    meta: MetaService, als: FakeMetaAls, clock: FakeClock
) -> None:
    first = await meta.map_rotation()
    clock.now += 61.0
    als.error = UpstreamError("down")

    for _ in range(5):
        assert await meta.map_rotation() == first
    assert als.rotation_calls == 2

    clock.now += 31.0
    await meta.map_rotation()
    assert als.rotation_calls == 3


async def test_recovery_after_an_outage_serves_fresh_data(
    meta: MetaService, als: FakeMetaAls, clock: FakeClock
) -> None:
    await meta.map_rotation()
    clock.now += 61.0
    als.error = UpstreamError("down")
    await meta.map_rotation()

    als.error = None
    clock.now += 31.0
    await meta.map_rotation()
    await meta.map_rotation()
    assert als.rotation_calls == 3


async def test_repeated_failures_with_nothing_cached_are_not_retried_at_once(
    meta: MetaService, als: FakeMetaAls
) -> None:
    als.error = UpstreamError("down")
    for _ in range(3):
        with pytest.raises(UpstreamError):
            await meta.map_rotation()
    assert als.rotation_calls == 1


async def test_failure_with_nothing_cached_raises(meta: MetaService, als: FakeMetaAls) -> None:
    als.error = UpstreamError("down")
    with pytest.raises(UpstreamError):
        await meta.map_rotation()
