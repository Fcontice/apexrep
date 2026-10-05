from datetime import datetime

from pydantic import BaseModel

from apexrep.als.models import PredatorThreshold
from apexrep.platforms import PlatformSlug
from apexrep.players.matches import MatchKind
from apexrep.players.repo import HistoryPoint


class ErrorResponse(BaseModel):
    detail: str


class ResolveResponse(BaseModel):
    uid: str
    platform: PlatformSlug
    name: str


class TrackResponse(BaseModel):
    is_tracked: bool
    tracked_since: datetime


class PlayerProfile(BaseModel):
    uid: str
    platform: PlatformSlug
    name: str
    level: int
    level_prestige: int
    level_progress: int
    rank_name: str | None
    rank_div: int | None
    rank_score: int | None
    selected_legend: str | None
    trackers: dict[str, int]
    is_tracked: bool
    tracked_since: datetime | None
    last_updated: datetime
    stale: bool


class HistoryResponse(BaseModel):
    points: list[HistoryPoint]
    bucketed: bool


class MatchItem(BaseModel):
    id: int
    kind: MatchKind
    detected_at: datetime
    legend: str | None
    level_progress_delta: int | None
    rank_score_delta: int | None
    tracker_deltas: dict[str, int]


class MatchesResponse(BaseModel):
    items: list[MatchItem]
    # Pass as `before` to get the next, older page; null on the last page.
    next_cursor: str | None


class SitemapPlayer(BaseModel):
    platform: PlatformSlug
    uid: str
    last_updated: datetime | None


class SitemapResponse(BaseModel):
    players: list[SitemapPlayer]


class PredatorResponse(BaseModel):
    pc: PredatorThreshold | None
    ps: PredatorThreshold | None
    xbox: PredatorThreshold | None
