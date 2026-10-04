from pydantic import BaseModel, Field, JsonValue, ValidationError, field_validator

from apexrep.als.errors import UpstreamError
from apexrep.als.models import Platform, PlayerSnapshot


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _to_uid(value: object) -> object:
    # ALS has returned UIDs both as numbers and as strings.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


class _Rank(BaseModel):
    rank_score: int | None = Field(default=None, alias="rankScore")
    rank_name: str | None = Field(default=None, alias="rankName")
    rank_div: int | None = Field(default=None, alias="rankDiv")

    @field_validator("rank_score", "rank_div", mode="before")
    @classmethod
    def _coerce_int(cls, value: object) -> int | None:
        return _to_int(value)


class _Global(BaseModel):
    name: str = ""
    uid: str
    level: int
    level_prestige: int = Field(default=0, alias="levelPrestige")
    level_progress: int = Field(alias="toNextLevelPercent")
    rank: _Rank = _Rank()

    @field_validator("uid", mode="before")
    @classmethod
    def _coerce_uid(cls, value: object) -> object:
        return _to_uid(value)


class _Tracker(BaseModel):
    key: str | None = None
    value: int | None = None

    @field_validator("value", mode="before")
    @classmethod
    def _coerce_value(cls, value: object) -> int | None:
        return _to_int(value)


class _SelectedLegend(BaseModel):
    legend_name: str | None = Field(default=None, alias="LegendName")
    data: list[_Tracker] = []


class _Legends(BaseModel):
    selected: _SelectedLegend = _SelectedLegend()


class _Realtime(BaseModel):
    selected_legend: str | None = Field(default=None, alias="selectedLegend")


class _BridgeResponse(BaseModel):
    global_: _Global = Field(alias="global")
    legends: _Legends = _Legends()
    realtime: _Realtime = _Realtime()


def parse_bridge(body: JsonValue, platform: Platform) -> PlayerSnapshot:
    try:
        bridge = _BridgeResponse.model_validate(body)
    except ValidationError as exc:
        raise UpstreamError(f"unexpected /bridge response shape: {exc}") from exc

    trackers: dict[str, int] = {
        tracker.key: tracker.value
        for tracker in bridge.legends.selected.data
        if tracker.key and tracker.value is not None
    }
    return PlayerSnapshot(
        uid=bridge.global_.uid,
        platform=platform,
        name=bridge.global_.name,
        level=bridge.global_.level,
        level_prestige=bridge.global_.level_prestige,
        level_progress=bridge.global_.level_progress,
        rank_name=bridge.global_.rank.rank_name,
        rank_div=bridge.global_.rank.rank_div,
        rank_score=bridge.global_.rank.rank_score,
        selected_legend=bridge.legends.selected.legend_name or bridge.realtime.selected_legend,
        trackers=trackers,
        raw=body,
    )
