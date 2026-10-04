from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, Request, Response, status

from apexrep.config import Settings, get_settings
from apexrep.db import Pool, create_pool
from apexrep.health import DatabaseProbe, HealthResponse, HealthStatus, evaluate_health
from apexrep.heartbeat import fetch_heartbeat


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    pool: Pool = await create_pool(get_settings())
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.close()


app = FastAPI(title="apexrep", lifespan=lifespan)


async def probe_database(request: Request) -> DatabaseProbe:
    pool: Pool = request.app.state.pool
    try:
        heartbeat_at = await fetch_heartbeat(pool)
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError):
        return DatabaseProbe(database=False, heartbeat_at=None)
    return DatabaseProbe(database=True, heartbeat_at=heartbeat_at)


@app.get("/api/health")
async def health(
    response: Response,
    probe: Annotated[DatabaseProbe, Depends(probe_database)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HealthResponse:
    result = evaluate_health(
        probe,
        now=datetime.now(UTC),
        stale_after_s=settings.worker_heartbeat_stale_s,
    )
    if result.status is HealthStatus.DOWN:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
