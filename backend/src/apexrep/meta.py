import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from apexrep.als.errors import AlsError
from apexrep.als.models import MapRotation, Platform, PredatorThreshold
from apexrep.als.rate_limiter import Clock
from apexrep.config import Settings


class MetaGateway(Protocol):
    async def map_rotation(self) -> MapRotation: ...

    async def predator(self) -> dict[Platform, PredatorThreshold]: ...


class TtlCache[T]:
    """Caches one value for `ttl_s`.

    Concurrent refreshes share one fetch. A failed refresh serves the previous
    value if there is one, and is not retried for `retry_after_failure_s`, so an
    outage costs one upstream attempt per interval rather than one per request.
    """

    def __init__(
        self,
        fetch: Callable[[], Awaitable[T]],
        *,
        ttl_s: float,
        retry_after_failure_s: float,
        clock: Clock,
    ) -> None:
        self._fetch: Callable[[], Awaitable[T]] = fetch
        self._ttl_s: float = ttl_s
        self._retry_after_failure_s: float = retry_after_failure_s
        self._clock: Clock = clock
        self._value: T | None = None
        self._expires_at: float = 0.0
        self._failure: AlsError | None = None
        self._failed_until: float = 0.0
        self._refresh: asyncio.Task[T] | None = None

    async def get(self) -> T:
        now = self._clock()
        if self._value is not None and now < self._expires_at:
            return self._value
        if self._failure is not None and now < self._failed_until:
            return self._stale_or_raise(self._failure)

        if self._refresh is None:
            self._refresh = asyncio.create_task(self._load())
            self._refresh.add_done_callback(self._clear_refresh)
        try:
            return await asyncio.shield(self._refresh)
        except AlsError as exc:
            return self._stale_or_raise(exc)

    def _stale_or_raise(self, error: AlsError) -> T:
        if self._value is None:
            raise error
        return self._value

    async def _load(self) -> T:
        try:
            value = await self._fetch()
        except AlsError as exc:
            self._failure = exc
            self._failed_until = self._clock() + self._retry_after_failure_s
            raise
        self._value = value
        self._failure = None
        self._expires_at = self._clock() + self._ttl_s
        return value

    def _clear_refresh(self, task: asyncio.Task[T]) -> None:
        self._refresh = None
        # Retrieve the exception so an unawaited failure is not logged as unhandled.
        if not task.cancelled():
            task.exception()


class MetaService:
    def __init__(
        self, *, als: MetaGateway, settings: Settings, clock: Clock = time.monotonic
    ) -> None:
        self._maps: TtlCache[MapRotation] = TtlCache(
            als.map_rotation,
            ttl_s=settings.meta_maps_ttl_s,
            retry_after_failure_s=settings.meta_retry_after_failure_s,
            clock=clock,
        )
        self._predator: TtlCache[dict[Platform, PredatorThreshold]] = TtlCache(
            als.predator,
            ttl_s=settings.meta_predator_ttl_s,
            retry_after_failure_s=settings.meta_retry_after_failure_s,
            clock=clock,
        )

    async def map_rotation(self) -> MapRotation:
        return await self._maps.get()

    async def predator(self) -> dict[Platform, PredatorThreshold]:
        return await self._predator.get()
