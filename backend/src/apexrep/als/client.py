import asyncio

import httpx
from pydantic import JsonValue

from apexrep.als.errors import UpstreamError, error_for_body, error_for_status, error_message
from apexrep.als.models import MapRotation, Platform, PlayerSnapshot, PredatorThreshold
from apexrep.als.parser import parse_bridge, parse_map_rotation, parse_predator
from apexrep.als.rate_limiter import RateLimiter, Sleep
from apexrep.config import Settings


class AlsClient:
    """The only place that calls the Apex Legends Status API."""

    def __init__(
        self,
        *,
        http: httpx.AsyncClient,
        api_key: str,
        rate_limiter: RateLimiter,
        max_retries: int,
        retry_backoff_s: float,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._http: httpx.AsyncClient = http
        self._api_key: str = api_key
        self._rate_limiter: RateLimiter = rate_limiter
        self._max_retries: int = max_retries
        self._retry_backoff_s: float = retry_backoff_s
        self._sleep: Sleep = sleep
        self.last_current_rate: int | None = None

    async def bridge_by_uid(self, uid: str, platform: Platform) -> PlayerSnapshot:
        return await self._bridge({"uid": uid}, platform)

    async def bridge_by_name(self, name: str, platform: Platform) -> PlayerSnapshot:
        """Resolve a name to a player. Used instead of /nametouid, which fails for
        PC names that /bridge resolves."""
        return await self._bridge({"player": name}, platform)

    async def _bridge(self, identity: dict[str, str], platform: Platform) -> PlayerSnapshot:
        body = await self._get_json(
            "/bridge",
            {**identity, "platform": platform.value, "merge": "1", "removeMerged": "1"},
        )
        return parse_bridge(body, platform)

    async def map_rotation(self) -> MapRotation:
        return parse_map_rotation(await self._get_json("/maprotation", {"version": "2"}))

    async def predator(self) -> dict[Platform, PredatorThreshold]:
        return parse_predator(await self._get_json("/predator", {}))

    def backlog_s(self) -> float:
        return self._rate_limiter.backlog_s()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get_json(self, path: str, params: dict[str, str]) -> JsonValue:
        attempt = 0
        while True:
            await self._rate_limiter.acquire()
            try:
                return await self._request_once(path, params)
            except UpstreamError:
                if attempt >= self._max_retries:
                    raise
                await self._sleep(self._retry_backoff_s * 2**attempt)
                attempt += 1

    async def _request_once(self, path: str, params: dict[str, str]) -> JsonValue:
        try:
            response = await self._http.get(
                path, params=params, headers={"Authorization": self._api_key}
            )
        except httpx.TransportError as exc:
            raise UpstreamError(f"ALS request failed: {exc!r}") from exc

        self._record_current_rate(response)

        body: JsonValue
        try:
            body = response.json()
        except ValueError:
            body = None
        message = error_message(body)

        if response.status_code != httpx.codes.OK:
            raise error_for_status(response.status_code, message or response.reason_phrase)
        if body is None:
            raise UpstreamError(f"ALS returned a non-JSON body for {path}")
        # ALS can answer 200 with an error body, including when rate limited.
        if message is not None:
            raise error_for_body(message)
        return body

    def _record_current_rate(self, response: httpx.Response) -> None:
        header = response.headers.get("X-Current-Rate")
        if header is not None and header.isdigit():
            self.last_current_rate = int(header)


def build_als_client(settings: Settings, *, rate_per_s: float) -> AlsClient:
    return AlsClient(
        http=httpx.AsyncClient(base_url=settings.als_base_url, timeout=settings.als_timeout_s),
        api_key=settings.als_api_key.get_secret_value(),
        rate_limiter=RateLimiter(rate_per_s),
        max_retries=settings.als_max_retries,
        retry_backoff_s=settings.als_retry_backoff_s,
    )
