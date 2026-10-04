from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel


class MatchKind(StrEnum):
    MATCH = "match"
    SESSION_GAP = "session_gap"


class MatchDraft(BaseModel):
    kind: MatchKind
    legend: str | None
    level_progress_delta: int | None
    rank_score_delta: int | None
    tracker_deltas: dict[str, int]


class SnapshotFields(Protocol):
    """The fields match detection reads; both stored and freshly parsed snapshots fit."""

    @property
    def level(self) -> int: ...
    @property
    def level_prestige(self) -> int: ...
    @property
    def level_progress(self) -> int: ...
    @property
    def rank_score(self) -> int | None: ...
    @property
    def selected_legend(self) -> str | None: ...
    @property
    def trackers(self) -> dict[str, int]: ...


def _progress(snapshot: SnapshotFields) -> tuple[int, int, int]:
    # `level` restarts at each prestige, so prestige has to lead the comparison.
    return (snapshot.level_prestige, snapshot.level, snapshot.level_progress)


def detect_match(
    prev: SnapshotFields,
    new: SnapshotFields,
    *,
    gap_s: float | None,
    session_gap_s: float,
    record_gaps: bool,
) -> MatchDraft | None:
    """Compare a player's latest stored snapshot with a new one.

    `gap_s` is the time since the player's previous successful poll, which can be
    much shorter than the age of `prev`: snapshots are only stored on change.
    One returned match means "one or more matches" inside the polling window.
    """
    same_legend = prev.selected_legend == new.selected_legend
    # Trackers can be re-equipped without a legend swap, so only keys present in
    # both snapshots are compared.
    tracker_deltas: dict[str, int] = (
        {
            key: new.trackers[key] - value
            for key, value in prev.trackers.items()
            if key in new.trackers and new.trackers[key] > value
        }
        if same_legend
        else {}
    )
    progressed = _progress(new) > _progress(prev)
    # A rank score change alone is not a match: split and season resets move it.
    if not progressed and not tracker_deltas:
        return None

    if gap_s is None or gap_s > session_gap_s:
        if not record_gaps:
            return None
        return MatchDraft(
            kind=MatchKind.SESSION_GAP,
            legend=None,
            level_progress_delta=None,
            rank_score_delta=None,
            tracker_deltas={},
        )

    level_progress_delta: int | None = (
        (new.level - prev.level) * 100 + (new.level_progress - prev.level_progress)
        if new.level_prestige == prev.level_prestige
        else None
    )
    rank_score_delta: int | None = (
        new.rank_score - prev.rank_score
        if new.rank_score is not None and prev.rank_score is not None
        else None
    )
    return MatchDraft(
        kind=MatchKind.MATCH,
        legend=new.selected_legend,
        level_progress_delta=level_progress_delta,
        rank_score_delta=rank_score_delta,
        tracker_deltas=tracker_deltas,
    )
