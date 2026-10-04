from collections.abc import Callable

import httpx
import pytest
from pydantic import JsonValue

from apexrep.als.client import AlsClient
from apexrep.als.errors import (
    InvalidApiKey,
    PlayerNotFound,
    RateLimited,
    UnknownPlatform,
    UpstreamError,
)
from apexrep.als.models import Platform
from apexrep.als.rate_limiter import RateLimiter
from tests.conftest import load_fixture

pytestmark = pytest.mark.anyio

Handler = Callable[[httpx.Request], httpx.Response]

# Error messages ALS really returned on 2026-10-04.
NAMETOUID_NOT_FOUND_200: str = "Player not found. Please try again (err origin lookup)"
NAMETOUID_DECLINED_200: str = (
    "Your request has been declined because of server load issue, "
    "Origin refusing the connection or a wrong username."
)


class Harness:
    """An AlsClient wired to a mock transport, recording requests and backoff sleeps."""

    def __init__(self, handler: Handler, *, max_retries: int = 2) -> None:
        self.requests: list[httpx.Request] = []
        self.sleeps: list[float] = []

        def recording_handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return handler(request)

        self.client = AlsClient(
            http=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler), base_url="https://als.test"
            ),
            api_key="test-key",
            rate_limiter=RateLimiter(1000.0, sleep=self._limiter_sleep),
            max_retries=max_retries,
            retry_backoff_s=1.0,
            sleep=self._backoff_sleep,
        )

    async def _limiter_sleep(self, seconds: float) -> None:
        return None

    async def _backoff_sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def respond(status_code: int, body: JsonValue) -> Handler:
    return lambda request: httpx.Response(status_code, json=body)


async def test_bridge_by_uid_sends_key_and_merge_params_and_parses_snapshot() -> None:
    harness = Harness(respond(200, load_fixture("bridge_ok.json")))
    snapshot = await harness.client.bridge_by_uid("1011572188996", Platform.PC)

    request = harness.requests[0]
    assert request.url.path == "/bridge"
    assert dict(request.url.params) == {
        "uid": "1011572188996",
        "platform": "PC",
        "merge": "1",
        "removeMerged": "1",
    }
    assert request.headers["Authorization"] == "test-key"
    assert snapshot.level == 382
    assert snapshot.name == "vinyasaflowTTV"


async def test_bridge_by_name_resolves_player() -> None:
    harness = Harness(respond(200, load_fixture("bridge_ok.json")))
    snapshot = await harness.client.bridge_by_name("xXfrankX", Platform.PC)

    assert dict(harness.requests[0].url.params) == {
        "player": "xXfrankX",
        "platform": "PC",
        "merge": "1",
        "removeMerged": "1",
    }
    assert snapshot.uid == "1011572188996"


async def test_recorded_404_is_player_not_found_and_not_retried() -> None:
    harness = Harness(respond(404, load_fixture("bridge_not_found.json")))
    with pytest.raises(PlayerNotFound):
        await harness.client.bridge_by_name("nobody", Platform.PC)
    assert len(harness.requests) == 1


async def test_rate_limited_200_body_is_rate_limited_and_not_retried() -> None:
    harness = Harness(respond(200, load_fixture("rate_limited_200.json")))
    with pytest.raises(RateLimited):
        await harness.client.bridge_by_uid("1", Platform.PC)
    assert len(harness.requests) == 1


async def test_not_found_200_body_is_player_not_found() -> None:
    harness = Harness(respond(200, {"Error": NAMETOUID_NOT_FOUND_200}))
    with pytest.raises(PlayerNotFound):
        await harness.client.bridge_by_name("nobody", Platform.PC)
    assert len(harness.requests) == 1


async def test_ambiguous_declined_200_body_is_retried_as_upstream_error() -> None:
    harness = Harness(respond(200, {"Error": NAMETOUID_DECLINED_200}), max_retries=1)
    with pytest.raises(UpstreamError):
        await harness.client.bridge_by_name("someone", Platform.PC)
    assert len(harness.requests) == 2


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(403, InvalidApiKey), (410, UnknownPlatform), (429, RateLimited)],
)
async def test_status_codes_map_to_typed_errors(
    status_code: int, expected: type[Exception]
) -> None:
    harness = Harness(respond(status_code, {"Error": "nope"}))
    with pytest.raises(expected):
        await harness.client.bridge_by_uid("1", Platform.PC)
    assert len(harness.requests) == 1


async def test_upstream_error_is_retried_with_backoff_then_succeeds() -> None:
    responses = iter(
        [
            httpx.Response(500, json={"Error": "internal"}),
            httpx.Response(405, json={"Error": "external API error"}),
            httpx.Response(200, json=load_fixture("bridge_ok.json")),
        ]
    )
    harness = Harness(lambda request: next(responses))
    snapshot = await harness.client.bridge_by_uid("1", Platform.PC)

    assert snapshot.level == 382
    assert len(harness.requests) == 3
    assert harness.sleeps == [1.0, 2.0]


async def test_upstream_error_raises_after_retries_are_exhausted() -> None:
    harness = Harness(respond(400, {"Error": "try again in a few minutes"}), max_retries=2)
    with pytest.raises(UpstreamError):
        await harness.client.bridge_by_uid("1", Platform.PC)
    assert len(harness.requests) == 3


async def test_transport_failure_is_retried_as_upstream_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    harness = Harness(fail, max_retries=1)
    with pytest.raises(UpstreamError):
        await harness.client.bridge_by_uid("1", Platform.PC)
    assert len(harness.requests) == 2


async def test_non_json_200_body_is_upstream_error() -> None:
    harness = Harness(lambda request: httpx.Response(200, text="<html>oops</html>"), max_retries=0)
    with pytest.raises(UpstreamError):
        await harness.client.bridge_by_uid("1", Platform.PC)


async def test_current_rate_header_is_recorded() -> None:
    harness = Harness(
        lambda request: httpx.Response(
            200, json=load_fixture("bridge_ok.json"), headers={"X-Current-Rate": "3"}
        )
    )
    await harness.client.bridge_by_uid("1", Platform.PC)
    assert harness.client.last_current_rate == 3
