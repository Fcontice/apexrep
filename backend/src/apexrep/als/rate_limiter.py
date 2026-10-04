import asyncio
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[None]]


class RateLimiter:
    """Spaces calls evenly so no more than `rate_per_s` start in any second.

    In-process only: the API and the worker each own one, with separate budgets.
    """

    def __init__(
        self,
        rate_per_s: float,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be positive")
        self._interval: float = 1.0 / rate_per_s
        self._clock: Clock = clock
        self._sleep: Sleep = sleep
        self._next_slot: float = 0.0

    def backlog_s(self) -> float:
        """How long a call made now would wait for its slot."""
        return max(0.0, self._next_slot - self._clock())

    async def acquire(self) -> None:
        now = self._clock()
        slot = max(now, self._next_slot)
        self._next_slot = slot + self._interval
        delay = slot - now
        if delay > 0:
            await self._sleep(delay)
