from datetime import UTC, datetime

from apexrep.players.matches import MatchDraft, MatchKind, detect_match
from apexrep.players.repo import StoredSnapshot

SESSION_GAP_S: float = 1800.0


def snap(
    *,
    level: int = 100,
    prestige: int = 1,
    progress: int = 40,
    rank_score: int | None = 5000,
    legend: str | None = "Octane",
    trackers: dict[str, int] | None = None,
) -> StoredSnapshot:
    return StoredSnapshot(
        taken_at=datetime(2026, 10, 4, tzinfo=UTC),
        level=level,
        level_prestige=prestige,
        level_progress=progress,
        rank_name="Gold",
        rank_div=2,
        rank_score=rank_score,
        selected_legend=legend,
        trackers=trackers if trackers is not None else {"kills": 100, "damage": 50_000},
    )


def detect(
    prev: StoredSnapshot,
    new: StoredSnapshot,
    *,
    gap_s: float | None = 240.0,
    record_gaps: bool = True,
) -> MatchDraft | None:
    return detect_match(
        prev, new, gap_s=gap_s, session_gap_s=SESSION_GAP_S, record_gaps=record_gaps
    )


def test_same_legend_records_progress_rank_and_positive_tracker_deltas() -> None:
    prev = snap()
    new = snap(progress=47, rank_score=5035, trackers={"kills": 103, "damage": 51_200})
    match = detect(prev, new)

    assert match is not None
    assert match.kind is MatchKind.MATCH
    assert match.legend == "Octane"
    assert match.level_progress_delta == 7
    assert match.rank_score_delta == 35
    assert match.tracker_deltas == {"kills": 3, "damage": 1_200}


def test_legend_swap_records_the_match_without_tracker_deltas() -> None:
    prev = snap()
    new = snap(progress=45, legend="Wraith", trackers={"kills": 900, "damage": 1})
    match = detect(prev, new)

    assert match is not None
    assert match.legend == "Wraith"
    assert match.level_progress_delta == 5
    assert match.tracker_deltas == {}


def test_legend_swap_alone_is_not_a_match() -> None:
    assert detect(snap(), snap(legend="Wraith", trackers={"kills": 900})) is None


def test_tracker_re_equip_only_compares_keys_present_in_both() -> None:
    prev = snap(trackers={"kills": 100, "damage": 50_000})
    new = snap(progress=42, trackers={"kills": 101, "wins": 7})
    match = detect(prev, new)

    assert match is not None
    assert match.tracker_deltas == {"kills": 1}


def test_tracker_re_equip_alone_is_not_a_match() -> None:
    prev = snap(trackers={"kills": 100})
    new = snap(trackers={"wins": 7})
    assert detect(prev, new) is None


def test_tracker_increase_without_level_progress_is_a_match() -> None:
    match = detect(snap(), snap(trackers={"kills": 101, "damage": 50_000}))

    assert match is not None
    assert match.level_progress_delta == 0
    assert match.tracker_deltas == {"kills": 1}


def test_tracker_decrease_is_ignored() -> None:
    assert detect(snap(), snap(trackers={"kills": 90, "damage": 50_000})) is None


def test_level_up_wraps_the_progress_delta() -> None:
    match = detect(snap(level=100, progress=90), snap(level=101, progress=5))

    assert match is not None
    assert match.level_progress_delta == 15


def test_prestige_change_is_a_match_with_no_progress_delta() -> None:
    match = detect(snap(level=500, prestige=1, progress=95), snap(level=1, prestige=2, progress=3))

    assert match is not None
    assert match.kind is MatchKind.MATCH
    assert match.level_progress_delta is None


def test_lower_level_on_the_same_prestige_is_not_progress() -> None:
    assert detect(snap(level=100), snap(level=99)) is None


def test_rank_only_change_is_not_a_match() -> None:
    assert detect(snap(rank_score=5000), snap(rank_score=1000)) is None


def test_no_change_is_not_a_match() -> None:
    assert detect(snap(), snap()) is None


def test_missing_rank_score_gives_no_rank_delta() -> None:
    match = detect(snap(rank_score=None), snap(progress=45))

    assert match is not None
    assert match.rank_score_delta is None


def test_progress_after_a_long_gap_is_a_session_gap_without_deltas() -> None:
    new = snap(progress=60, trackers={"kills": 110, "damage": 60_000})
    match = detect(snap(), new, gap_s=1801.0)

    assert match is not None
    assert match.kind is MatchKind.SESSION_GAP
    assert match.legend is None
    assert match.level_progress_delta is None
    assert match.rank_score_delta is None
    assert match.tracker_deltas == {}


def test_progress_exactly_at_the_gap_window_is_still_a_match() -> None:
    match = detect(snap(), snap(progress=60), gap_s=SESSION_GAP_S)

    assert match is not None
    assert match.kind is MatchKind.MATCH


def test_session_gap_is_not_recorded_for_untracked_players() -> None:
    assert detect(snap(), snap(progress=60), gap_s=7200.0, record_gaps=False) is None


def test_unknown_gap_is_treated_as_a_session_gap() -> None:
    match = detect(snap(), snap(progress=60), gap_s=None)

    assert match is not None
    assert match.kind is MatchKind.SESSION_GAP
