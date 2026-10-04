from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from apexrep.api.app import app, probe_database
from apexrep.config import Settings, get_settings
from apexrep.health import DatabaseProbe, HealthStatus, evaluate_health

NOW: datetime = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
STALE_AFTER_S: float = 90.0


def test_fresh_heartbeat_is_ok() -> None:
    probe = DatabaseProbe(database=True, heartbeat_at=NOW - timedelta(seconds=30))
    result = evaluate_health(probe, now=NOW, stale_after_s=STALE_AFTER_S)
    assert result.status is HealthStatus.OK
    assert result.worker_alive is True


def test_stale_heartbeat_is_degraded() -> None:
    probe = DatabaseProbe(database=True, heartbeat_at=NOW - timedelta(seconds=91))
    result = evaluate_health(probe, now=NOW, stale_after_s=STALE_AFTER_S)
    assert result.status is HealthStatus.DEGRADED
    assert result.worker_alive is False


def test_missing_heartbeat_is_degraded() -> None:
    probe = DatabaseProbe(database=True, heartbeat_at=None)
    result = evaluate_health(probe, now=NOW, stale_after_s=STALE_AFTER_S)
    assert result.status is HealthStatus.DEGRADED


def test_database_down_is_down() -> None:
    probe = DatabaseProbe(database=False, heartbeat_at=None)
    result = evaluate_health(probe, now=NOW, stale_after_s=STALE_AFTER_S)
    assert result.status is HealthStatus.DOWN


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql://unused", worker_heartbeat_stale_s=STALE_AFTER_S
    )
    # No context manager: the lifespan (and its database pool) is not started.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_route_ok(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: DatabaseProbe(
        database=True, heartbeat_at=datetime.now(UTC)
    )
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] is True
    assert body["worker_alive"] is True


def test_health_route_returns_503_when_database_down(client: TestClient) -> None:
    app.dependency_overrides[probe_database] = lambda: DatabaseProbe(
        database=False, heartbeat_at=None
    )
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "down"
