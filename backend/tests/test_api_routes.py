from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from apexrep.als.errors import PlayerNotFound, UpstreamError
from apexrep.als.models import Platform
from apexrep.api.app import app
from apexrep.api.deps import get_player_service, is_crawler
from apexrep.config import Settings, get_settings
from apexrep.players.repo import StoredPlayer, StoredSnapshot, TrackingFull
from apexrep.players.service import ProfileResult, ProfileUnavailable, ResolvedPlayer

TOKEN: str = "test-token"
AUTH: dict[str, str] = {"X-Internal-Token": TOKEN}
BROWSER_UA: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36"
NOW: datetime = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


class FakePlayerService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.resolve_calls: list[tuple[Platform, str]] = []
        self.profile_calls: list[tuple[Platform, str, bool]] = []
        self.track_calls: list[tuple[Platform, str]] = []

    async def resolve(self, platform: Platform, name: str) -> ResolvedPlayer:
        self.resolve_calls.append((platform, name))
        if self.error is not None:
            raise self.error
        return ResolvedPlayer(uid="1011572188996", platform=platform, name="vinyasaflowTTV")

    async def track(self, platform: Platform, uid: str) -> datetime:
        self.track_calls.append((platform, uid))
        if self.error is not None:
            raise self.error
        return NOW

    async def get_profile(self, platform: Platform, uid: str, *, is_crawler: bool) -> ProfileResult:
        self.profile_calls.append((platform, uid, is_crawler))
        if self.error is not None:
            raise self.error
        snapshot = StoredSnapshot(
            taken_at=NOW,
            level=382,
            level_prestige=1,
            level_progress=11,
            rank_name="Diamond",
            rank_div=4,
            rank_score=12747,
            selected_legend="Octane",
            trackers={"career_kills": 12988},
        )
        player = StoredPlayer(
            uid=uid,
            platform=platform,
            current_name="vinyasaflowTTV",
            is_tracked=False,
            tracked_since=None,
            last_polled_at=NOW,
            polled_age_s=10.0,
            snapshot=snapshot,
        )
        return ProfileResult(player=player, snapshot=snapshot, stale=False)


@pytest.fixture
def players() -> FakePlayerService:
    return FakePlayerService()


@pytest.fixture
def client(players: FakePlayerService) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused", internal_token=SecretStr(TOKEN)
    )
    app.dependency_overrides[get_player_service] = lambda: players
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_routes_reject_a_missing_or_wrong_token(client: TestClient) -> None:
    assert client.get("/api/resolve", params={"platform": "pc", "name": "x"}).status_code == 403
    wrong = client.get(
        "/api/resolve",
        params={"platform": "pc", "name": "x"},
        headers={"X-Internal-Token": "wrong"},
    )
    assert wrong.status_code == 403


def test_an_unset_token_rejects_everything(client: TestClient) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(database_url="postgresql://unused")
    response = client.get(
        "/api/resolve", params={"platform": "pc", "name": "x"}, headers={"X-Internal-Token": ""}
    )
    assert response.status_code == 403


def test_resolve_maps_the_platform_slug_and_returns_the_player(
    client: TestClient, players: FakePlayerService
) -> None:
    response = client.get(
        "/api/resolve", params={"platform": "xbox", "name": "Some Name"}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.json() == {"uid": "1011572188996", "platform": "xbox", "name": "vinyasaflowTTV"}
    assert players.resolve_calls == [(Platform.X1, "Some Name")]


def test_resolve_rejects_an_unknown_platform(client: TestClient) -> None:
    response = client.get("/api/resolve", params={"platform": "switch", "name": "x"}, headers=AUTH)
    assert response.status_code == 422


def test_resolve_not_found_is_404(client: TestClient, players: FakePlayerService) -> None:
    players.error = PlayerNotFound("nope")
    response = client.get("/api/resolve", params={"platform": "pc", "name": "x"}, headers=AUTH)
    assert response.status_code == 404
    assert response.json() == {"detail": "player_not_found"}


def test_resolve_upstream_failure_is_503(client: TestClient, players: FakePlayerService) -> None:
    players.error = UpstreamError("down")
    response = client.get("/api/resolve", params={"platform": "pc", "name": "x"}, headers=AUTH)
    assert response.status_code == 503
    assert response.json() == {"detail": "upstream_unavailable"}


def test_profile_returns_the_player_profile(client: TestClient, players: FakePlayerService) -> None:
    response = client.get(
        "/api/players/pc/1011572188996",
        headers={**AUTH, "X-Client-User-Agent": BROWSER_UA, "X-Client-IP": "203.0.113.5"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["platform"] == "pc"
    assert body["name"] == "vinyasaflowTTV"
    assert body["level"] == 382
    assert body["level_prestige"] == 1
    assert body["trackers"] == {"career_kills": 12988}
    assert body["stale"] is False
    assert players.profile_calls == [(Platform.PC, "1011572188996", False)]


def test_profile_flags_crawlers(client: TestClient, players: FakePlayerService) -> None:
    client.get(
        "/api/players/pc/1",
        headers={**AUTH, "X-Client-User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
    )
    assert players.profile_calls == [(Platform.PC, "1", True)]


def test_profile_rejects_a_non_numeric_uid(client: TestClient) -> None:
    assert client.get("/api/players/pc/not-a-uid", headers=AUTH).status_code == 422


def test_profile_unavailable_is_503(client: TestClient, players: FakePlayerService) -> None:
    players.error = ProfileUnavailable("down")
    assert client.get("/api/players/pc/1", headers=AUTH).status_code == 503


def test_track_starts_tracking(client: TestClient, players: FakePlayerService) -> None:
    response = client.post("/api/players/ps/42/track", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"is_tracked": True, "tracked_since": "2026-10-04T12:00:00Z"}
    assert players.track_calls == [(Platform.PS4, "42")]


def test_track_requires_the_token(client: TestClient) -> None:
    assert client.post("/api/players/pc/42/track").status_code == 403


def test_track_when_full_is_409(client: TestClient, players: FakePlayerService) -> None:
    players.error = TrackingFull()
    response = client.post("/api/players/pc/42/track", headers=AUTH)
    assert response.status_code == 409
    assert response.json() == {"detail": "tracking_full"}


def test_track_unknown_player_is_404(client: TestClient, players: FakePlayerService) -> None:
    players.error = PlayerNotFound("unknown")
    assert client.post("/api/players/pc/42/track", headers=AUTH).status_code == 404


def test_health_needs_no_token() -> None:
    routes = {getattr(route, "path", "") for route in app.routes}
    assert "/api/health" in routes


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        (BROWSER_UA, False),
        ("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)", True),
        ("Mozilla/5.0 (compatible; bingbot/2.0)", True),
        ("facebookexternalhit/1.1", True),
        ("Twitterbot/1.0", True),
        ("curl/8.5.0", True),
        ("", True),
        (None, True),
    ],
)
def test_is_crawler(user_agent: str | None, expected: bool) -> None:
    assert is_crawler(user_agent) is expected
