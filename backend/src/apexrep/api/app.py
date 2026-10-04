import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from apexrep.als.client import build_als_client
from apexrep.als.errors import AlsError, PlayerNotFound
from apexrep.api.routes import router
from apexrep.config import Settings, get_settings
from apexrep.db import Pool, create_pool
from apexrep.health import DatabaseProbe, HealthResponse, HealthStatus, evaluate_health
from apexrep.heartbeat import fetch_heartbeat
from apexrep.players.repo import TrackingFull
from apexrep.players.service import PlayerService, ProfileUnavailable

logger = logging.getLogger("apexrep.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool: Pool = await create_pool(settings)
    als = build_als_client(settings, rate_per_s=settings.als_rate_backend_per_s)
    app.state.pool = pool
    app.state.players = PlayerService(pool=pool, als=als, settings=settings)
    try:
        yield
    finally:
        await als.aclose()
        await pool.close()


app = FastAPI(title="apexrep", lifespan=lifespan)
app.include_router(router)


@app.exception_handler(PlayerNotFound)
async def player_not_found_handler(request: Request, exc: PlayerNotFound) -> JSONResponse:
    return JSONResponse({"detail": "player_not_found"}, status_code=status.HTTP_404_NOT_FOUND)


@app.exception_handler(TrackingFull)
async def tracking_full_handler(request: Request, exc: TrackingFull) -> JSONResponse:
    return JSONResponse({"detail": "tracking_full"}, status_code=status.HTTP_409_CONFLICT)


@app.exception_handler(AlsError)
@app.exception_handler(ProfileUnavailable)
async def upstream_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("ALS unavailable for %s: %r", request.url.path, exc)
    return JSONResponse(
        {"detail": "upstream_unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE
    )


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
