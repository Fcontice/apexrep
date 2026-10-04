from datetime import datetime

from pydantic import BaseModel

from apexrep.platforms import PlatformSlug


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
