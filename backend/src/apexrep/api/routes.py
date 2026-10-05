from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from apexrep.als.models import MapRotation, Platform
from apexrep.api.cursor import InvalidCursor, decode_cursor, encode_cursor
from apexrep.api.deps import (
    ClientInfo,
    enforce_limit,
    get_client_info,
    get_ip_limiters,
    get_meta_service,
    get_player_service,
    limit_resolve,
    limit_track,
    require_internal_token,
)
from apexrep.api.ip_limit import IpLimiters
from apexrep.api.schemas import (
    ErrorResponse,
    HistoryResponse,
    MatchesResponse,
    MatchItem,
    PlayerProfile,
    PredatorResponse,
    ResolveResponse,
    SitemapPlayer,
    SitemapResponse,
    TrackResponse,
)
from apexrep.meta import MetaService
from apexrep.platforms import PlatformSlug, to_platform, to_slug
from apexrep.players.service import PlayerService

router = APIRouter(
    prefix="/api",
    dependencies=[Depends(require_internal_token)],
    responses={403: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)

RATE_LIMITED: dict[int | str, dict[str, object]] = {429: {"model": ErrorResponse}}

UID_PATTERN: str = r"^[0-9]{1,20}$"

PlayersDep = Annotated[PlayerService, Depends(get_player_service)]
MetaDep = Annotated[MetaService, Depends(get_meta_service)]
ClientDep = Annotated[ClientInfo, Depends(get_client_info)]
LimitersDep = Annotated[IpLimiters, Depends(get_ip_limiters)]
UidPath = Annotated[str, Path(pattern=UID_PATTERN)]


@router.get(
    "/resolve",
    dependencies=[Depends(limit_resolve)],
    responses={404: {"model": ErrorResponse}, **RATE_LIMITED},
)
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
    dependencies=[Depends(limit_track)],
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}, **RATE_LIMITED},
)
async def track_player(platform: PlatformSlug, uid: UidPath, players: PlayersDep) -> TrackResponse:
    """Idempotent. 409 when the tracked-player cap is full."""
    tracked_since = await players.track(to_platform(platform), uid)
    return TrackResponse(is_tracked=True, tracked_since=tracked_since)


@router.get("/players/{platform}/{uid}/history")
async def player_history(
    platform: PlatformSlug,
    uid: UidPath,
    players: PlayersDep,
    days: Annotated[int, Query(ge=1, le=3650)] = 30,
) -> HistoryResponse:
    """Snapshot series for charts, oldest first. days is capped by history_max_days."""
    history = await players.get_history(to_platform(platform), uid, days=days)
    return HistoryResponse(points=history.points, bucketed=history.bucketed)


@router.get("/players/{platform}/{uid}/matches")
async def player_matches(
    platform: PlatformSlug,
    uid: UidPath,
    players: PlayersDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: str | None = None,
) -> MatchesResponse:
    """Derived matches, newest first. One row can stand for more than one match."""
    try:
        cursor = decode_cursor(before) if before is not None else None
    except InvalidCursor as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid_cursor") from exc
    page = await players.get_matches(to_platform(platform), uid, limit=limit, before=cursor)
    return MatchesResponse(
        items=[MatchItem.model_validate(item, from_attributes=True) for item in page.items],
        next_cursor=encode_cursor(page.next_cursor) if page.next_cursor is not None else None,
    )


@router.get(
    "/players/{platform}/{uid}",
    responses={404: {"model": ErrorResponse}, **RATE_LIMITED},
)
async def player_profile(
    platform: PlatformSlug,
    uid: UidPath,
    players: PlayersDep,
    client: ClientDep,
    limiters: LimitersDep,
) -> PlayerProfile:
    als_platform = to_platform(platform)
    # Viewing a stored player is free. Viewing one the site has never seen costs an
    # ALS call, so it counts against the same per-visitor limit as a name lookup.
    if not client.is_crawler and not await players.is_known(als_platform, uid):
        enforce_limit(limiters.resolve, client)
    result = await players.get_profile(als_platform, uid, is_crawler=client.is_crawler)
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


@router.get("/sitemap/players")
async def sitemap_players(players: PlayersDep) -> SitemapResponse:
    """Tracked players, the only profiles the sitemap lists."""
    tracked = await players.list_tracked()
    return SitemapResponse(
        players=[
            SitemapPlayer(
                platform=to_slug(player.platform),
                uid=player.uid,
                last_updated=player.last_polled_at,
            )
            for player in tracked
        ]
    )


@router.get("/meta/maps")
async def meta_maps(meta: MetaDep) -> MapRotation:
    """Current and next map for pubs and ranked, cached for a minute."""
    return await meta.map_rotation()


@router.get("/meta/predator")
async def meta_predator(meta: MetaDep) -> PredatorResponse:
    """Rank score needed for Predator on each platform, cached for 15 minutes."""
    thresholds = await meta.predator()
    return PredatorResponse(
        pc=thresholds.get(Platform.PC),
        ps=thresholds.get(Platform.PS4),
        xbox=thresholds.get(Platform.X1),
    )
