from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, JsonValue


class Platform(StrEnum):
    PC = "PC"
    PS4 = "PS4"
    X1 = "X1"


class MapSlot(BaseModel):
    map: str
    start: datetime
    end: datetime


class ModeRotation(BaseModel):
    current: MapSlot
    next: MapSlot | None = None


class MapRotation(BaseModel):
    battle_royale: ModeRotation | None = None
    ranked: ModeRotation | None = None


class PredatorThreshold(BaseModel):
    # Rank score of the last Predator slot: what it takes to reach Predator.
    rank_score: int
    masters_and_preds: int
    updated_at: datetime


class PlayerSnapshot(BaseModel):
    uid: str
    platform: Platform
    name: str
    level: int
    # `level` restarts from 1 each time a player prestiges, so it is only
    # comparable together with `level_prestige`.
    level_prestige: int
    level_progress: int
    rank_name: str | None
    rank_div: int | None
    rank_score: int | None
    selected_legend: str | None
    trackers: dict[str, int]
    raw: JsonValue
