from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class DatabaseProbe(BaseModel):
    database: bool
    heartbeat_at: datetime | None


class HealthResponse(BaseModel):
    status: HealthStatus
    database: bool
    worker_alive: bool
    worker_heartbeat_at: datetime | None


def evaluate_health(probe: DatabaseProbe, *, now: datetime, stale_after_s: float) -> HealthResponse:
    worker_alive: bool = (
        probe.heartbeat_at is not None
        and (now - probe.heartbeat_at).total_seconds() <= stale_after_s
    )
    if not probe.database:
        status = HealthStatus.DOWN
    elif not worker_alive:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.OK
    return HealthResponse(
        status=status,
        database=probe.database,
        worker_alive=worker_alive,
        worker_heartbeat_at=probe.heartbeat_at,
    )
