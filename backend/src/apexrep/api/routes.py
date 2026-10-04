from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from apexrep.api.deps import (
    ClientInfo,
    get_client_info,
    get_player_service,
    require_internal_token,
)
from apexrep.api.schemas import ErrorResponse, PlayerProfile, ResolveResponse, TrackResponse
from apexrep.platforms import PlatformSlug, to_platform, to_slug
from apexrep.players.service import PlayerService

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_internal_token)],
    responses={403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)

UID_PATTERN: str = r"^[0-9]{1,20}$"

PlayersDep = Annotated[PlayerService, Depends(get_player_service)]
ClientDep = Annotated[ClientInfo, Depends(get_client_info)]


@router.get("/resolve", responses={404: {"model": ErrorResponse}})
async def resolve(
    platform: PlatformSlug,
    name: Annotated[str, Query(min_length=1, max_length=64)],
    players: PlayersDep,
) -> ResolveResponse:
    resolved = await players.resolve(to_platform(platform), name)
    return ResolveResponse(
        uid=resolved.uid, platform=to_slug(resolved.platform), name=resolved.name
    )


@router.post(
    "/players/{platform}/{uid}/track",
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def track_player(
    platform: PlatformSlug,
    uid: Annotated[str, Path(pattern=UID_PATTERN)],
    players: PlayersDep,
) -> TrackResponse:
    """Idempotent. 409 when the tracked-player cap is full."""
    tracked_since = await players.track(to_platform(platform), uid)
    return TrackResponse(is_tracked=True, tracked_since=tracked_since)


@router.get("/players/{platform}/{uid}", responses={404: {"model": ErrorResponse}})
async def player_profile(
    platform: PlatformSlug,
    uid: Annotated[str, Path(pattern=UID_PATTERN)],
    players: PlayersDep,
    client: ClientDep,
) -> PlayerProfile:
    result = await players.get_profile(to_platform(platform), uid, is_crawler=client.is_crawler)
    player, snapshot = result.player, result.snapshot
    return PlayerProfile(
        uid=player.uid,
        platform=to_slug(player.platform),
        name=player.current_name,
        level=snapshot.level,
        level_prestige=snapshot.level_prestige,
        level_progress=snapshot.level_progress,
        rank_name=snapshot.rank_name,
        rank_div=snapshot.rank_div,
        rank_score=snapshot.rank_score,
        selected_legend=snapshot.selected_legend,
        trackers=snapshot.trackers,
        is_tracked=player.is_tracked,
        tracked_since=player.tracked_since,
        last_updated=player.last_polled_at or snapshot.taken_at,
        stale=result.stale,
    )
