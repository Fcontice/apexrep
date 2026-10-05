import base64
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from apexrep.als.errors import PlayerNotFound, UpstreamError
from apexrep.als.models import MapRotation, Platform, PredatorThreshold
from apexrep.als.parser import parse_map_rotation, parse_predator
from apexrep.api.app import app
from apexrep.api.cursor import encode_cursor
from apexrep.api.deps import (
    get_ip_limiters,
    get_meta_service,
    get_player_service,
    is_crawler,
)
from apexrep.api.ip_limit import IpLimiters
from apexrep.config import Settings, get_settings
from apexrep.players.matches import MatchKind
from apexrep.players.repo import (
    History,
    HistoryPoint,
    MatchCursor,
    StoredMatch,
    StoredPlayer,
    StoredSnapshot,
    TrackedPlayer,
    TrackingFull,
)
from apexrep.players.service import (
    MatchPage,
    ProfileResult,
    ProfileUnavailable,
    ResolvedPlayer,
)
from tests.conftest import load_fixture

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
        self.history_days: list[int] = []
        self.matches_calls: list[tuple[int, MatchCursor | None]] = []
        self.known: bool = True

    async def is_known(self, platform: Platform, uid: str) -> bool:
        return self.known

    async def resolve(self, platform: Platform, name: str) -> ResolvedPlayer:
        self.resolve_calls.append((platform, name))
        if self.error is not None:
            raise self.error
        return ResolvedPlayer(uid="1011572188996", platform=platform, name="vinyasaflowTTV")

    async def get_history(self, platform: Platform, uid: str, *, days: int) -> History:
        self.history_days.append(days)
        point = HistoryPoint(
            taken_at=NOW,
            level=382,
            level_prestige=1,
            level_progress=11,
            rank_score=12747,
            selected_legend="Octane",
            trackers={"career_kills": 12988},
        )
        return History(points=[point], bucketed=False)

    async def get_matches(
        self, platform: Platform, uid: str, *, limit: int, before: MatchCursor | None
    ) -> MatchPage:
        self.matches_calls.append((limit, before))
        item = StoredMatch(
            id=7,
            kind=MatchKind.MATCH,
            detected_at=NOW,
            legend="Octane",
            level_progress_delta=3,
            rank_score_delta=25,
            tracker_deltas={"career_kills": 2},
        )
        return MatchPage(items=[item], next_cursor=MatchCursor(detected_at=NOW, id=7))

    async def list_tracked(self) -> list[TrackedPlayer]:
        return [TrackedPlayer(uid="42", platform=Platform.X1, last_polled_at=NOW)]

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


class FakeMetaService:
    async def map_rotation(self) -> MapRotation:
        return parse_map_rotation(load_fixture("maprotation_ok.json"))

    async def predator(self) -> dict[Platform, PredatorThreshold]:
        return parse_predator(load_fixture("predator_ok.json"))


@pytest.fixture
def players() -> FakePlayerService:
    return FakePlayerService()


@pytest.fixture
def client(players: FakePlayerService) -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused", internal_token=SecretStr(TOKEN)
    )
    app.dependency_overrides[get_player_service] = lambda: players
    app.dependency_overrides[get_meta_service] = FakeMetaService
    limiters = IpLimiters(
        Settings(
            _env_file=None,
            database_url="postgresql://unused",
            ip_limit_resolve_count=3,
            ip_limit_track_count=2,
        )
    )
    app.dependency_overrides[get_ip_limiters] = lambda: limiters
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


def test_history_returns_points_and_passes_days(
    client: TestClient, players: FakePlayerService
) -> None:
    response = client.get("/api/players/pc/42/history", params={"days": 7}, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["bucketed"] is False
    assert body["points"][0]["rank_score"] == 12747
    assert body["points"][0]["trackers"] == {"career_kills": 12988}
    assert players.history_days == [7]


def test_history_accepts_a_long_window_and_leaves_the_cap_to_the_service(
    client: TestClient, players: FakePlayerService
) -> None:
    response = client.get("/api/players/pc/42/history", params={"days": 365}, headers=AUTH)
    assert response.status_code == 200
    assert players.history_days == [365]


def test_history_rejects_nonsense_days(client: TestClient) -> None:
    assert (
        client.get("/api/players/pc/42/history", params={"days": 0}, headers=AUTH).status_code
        == 422
    )


def test_matches_returns_items_and_an_opaque_cursor(
    client: TestClient, players: FakePlayerService
) -> None:
    response = client.get("/api/players/pc/42/matches", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["kind"] == "match"
    assert body["items"][0]["tracker_deltas"] == {"career_kills": 2}
    assert players.matches_calls == [(50, None)]

    follow_up = client.get(
        "/api/players/pc/42/matches",
        params={"limit": 10, "before": body["next_cursor"]},
        headers=AUTH,
    )
    assert follow_up.status_code == 200
    assert players.matches_calls[1] == (10, MatchCursor(detected_at=NOW, id=7))


def test_matches_rejects_a_bad_cursor(client: TestClient) -> None:
    response = client.get("/api/players/pc/42/matches", params={"before": "junk"}, headers=AUTH)
    assert response.status_code == 422
    assert encode_cursor(MatchCursor(detected_at=NOW, id=1)) != "junk"


def test_meta_maps_returns_the_rotation(client: TestClient) -> None:
    response = client.get("/api/meta/maps", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["battle_royale"]["current"]["map"] == "Broken Moon"


def test_meta_predator_is_keyed_by_platform_slug(client: TestClient) -> None:
    response = client.get("/api/meta/predator", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"pc", "ps", "xbox"}
    assert body["pc"]["rank_score"] == 24798


def test_meta_requires_the_token(client: TestClient) -> None:
    assert client.get("/api/meta/maps").status_code == 403


def test_resolve_is_limited_per_visitor_ip(client: TestClient) -> None:
    def lookup(ip: str) -> int:
        status_code: int = client.get(
            "/api/resolve",
            params={"platform": "pc", "name": "x"},
            headers={**AUTH, "X-Client-IP": ip},
        ).status_code
        return status_code

    assert [lookup("203.0.113.5") for _ in range(4)] == [200, 200, 200, 429]
    assert lookup("203.0.113.6") == 200


def test_rate_limited_response_says_when_to_retry(client: TestClient) -> None:
    headers = {**AUTH, "X-Client-IP": "203.0.113.7"}
    for _ in range(3):
        client.get("/api/resolve", params={"platform": "pc", "name": "x"}, headers=headers)
    response = client.get("/api/resolve", params={"platform": "pc", "name": "x"}, headers=headers)

    assert response.status_code == 429
    assert response.json() == {"detail": "rate_limited"}
    assert 0 < int(response.headers["Retry-After"]) <= 300


def test_requests_without_a_forwarded_ip_share_one_limit(client: TestClient) -> None:
    statuses = [
        client.get("/api/resolve", params={"platform": "pc", "name": "x"}, headers=AUTH).status_code
        for _ in range(4)
    ]
    assert statuses == [200, 200, 200, 429]


def test_track_is_limited_per_visitor_ip(client: TestClient) -> None:
    headers = {**AUTH, "X-Client-IP": "203.0.113.8"}
    statuses = [
        client.post("/api/players/pc/42/track", headers=headers).status_code for _ in range(3)
    ]
    assert statuses == [200, 200, 429]


def test_profile_views_are_not_rate_limited(client: TestClient) -> None:
    headers = {**AUTH, "X-Client-IP": "203.0.113.9"}
    statuses = {client.get("/api/players/pc/42", headers=headers).status_code for _ in range(10)}
    assert statuses == {200}


def test_viewing_unknown_players_counts_against_the_lookup_limit(
    client: TestClient, players: FakePlayerService
) -> None:
    players.known = False
    headers = {**AUTH, "X-Client-IP": "203.0.113.10", "X-Client-User-Agent": BROWSER_UA}
    statuses = [
        client.get(f"/api/players/pc/{uid}", headers=headers).status_code for uid in range(1, 5)
    ]
    assert statuses == [200, 200, 200, 429]
    assert len(players.profile_calls) == 3


def test_crawlers_on_unknown_players_do_not_use_the_lookup_limit(
    client: TestClient, players: FakePlayerService
) -> None:
    players.known = False
    headers = {**AUTH, "X-Client-IP": "203.0.113.11", "X-Client-User-Agent": "Googlebot/2.1"}
    statuses = {client.get("/api/players/pc/7", headers=headers).status_code for _ in range(6)}
    assert statuses == {200}


def test_a_forged_cursor_with_an_oversized_id_is_rejected(client: TestClient) -> None:
    forged = base64.urlsafe_b64encode(
        b'{"detected_at":"2026-01-01T00:00:00Z","id":99999999999999999999}'
    ).decode()
    response = client.get("/api/players/pc/42/matches", params={"before": forged}, headers=AUTH)
    assert response.status_code == 422


def test_sitemap_lists_tracked_players(client: TestClient) -> None:
    response = client.get("/api/sitemap/players", headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {
        "players": [{"platform": "xbox", "uid": "42", "last_updated": "2026-10-04T12:00:00Z"}]
    }


def test_api_docs_are_not_exposed_by_default(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


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
