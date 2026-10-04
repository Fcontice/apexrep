import pytest

from apexrep.als.rate_limiter import RateLimiter

pytestmark = pytest.mark.anyio


class FakeTime:
    def __init__(self) -> None:
        self.now: float = 100.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


async def test_first_call_does_not_wait() -> None:
    fake = FakeTime()
    limiter = RateLimiter(4.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire()
    assert fake.sleeps == []


async def test_back_to_back_calls_are_spaced_by_the_interval() -> None:
    fake = FakeTime()
    limiter = RateLimiter(4.0, clock=fake.clock, sleep=fake.sleep)
    for _ in range(5):
        await limiter.acquire()
    assert fake.sleeps == pytest.approx([0.25, 0.25, 0.25, 0.25])
    assert fake.now == pytest.approx(101.0)


async def test_concurrent_callers_get_distinct_slots() -> None:
    fake = FakeTime()
    delays: list[float] = []

    async def record_only(seconds: float) -> None:
        delays.append(seconds)

    limiter = RateLimiter(2.0, clock=fake.clock, sleep=record_only)
    for _ in range(3):
        await limiter.acquire()
    assert delays == pytest.approx([0.5, 1.0])


async def test_idle_time_does_not_build_up_a_burst() -> None:
    fake = FakeTime()
    limiter = RateLimiter(4.0, clock=fake.clock, sleep=fake.sleep)
    await limiter.acquire()
    fake.now += 60.0
    await limiter.acquire()
    await limiter.acquire()
    assert fake.sleeps == pytest.approx([0.25])


def test_rate_must_be_positive() -> None:
    with pytest.raises(ValueError):
        RateLimiter(0)
