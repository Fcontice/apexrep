import pytest
from pydantic import JsonValue

from apexrep.als.errors import UpstreamError
from apexrep.als.models import Platform
from apexrep.als.parser import parse_bridge
from tests.conftest import load_fixture


def test_parse_bridge_extracts_snapshot_fields_from_recorded_response() -> None:
    body = load_fixture("bridge_ok.json")
    snapshot = parse_bridge(body, Platform.PC)

    assert snapshot.uid == "1011572188996"
    assert snapshot.platform is Platform.PC
    assert snapshot.name == "vinyasaflowTTV"
    assert snapshot.level == 382
    assert snapshot.level_prestige == 1
    assert snapshot.level_progress == 11
    assert snapshot.rank_name == "Diamond"
    assert snapshot.rank_div == 4
    assert snapshot.rank_score == 12747
    assert snapshot.selected_legend == "Octane"
    assert snapshot.trackers == {
        "career_kills": 12988,
        "passive_health_regen": 5019767,
        "damage": 2387825,
    }
    assert snapshot.raw == body


def test_parse_bridge_builds_flat_tracker_map_and_skips_empty_slots() -> None:
    # Tracker entries shaped like the ones under legends.all in the recorded response.
    body: JsonValue = {
        "global": {"name": "P", "uid": "1", "level": 10, "toNextLevelPercent": 5},
        "legends": {
            "selected": {
                "LegendName": "Revenant",
                "data": [
                    {
                        "name": "BR Kills",
                        "value": 279,
                        "key": "kills",
                        "rank": {"rankPos": 1053166, "topPercent": 46.61},
                        "rankPlatformSpecific": {
                            "rankPos": "NOT_CALCULATED_YET",
                            "topPercent": "NOT_CALCULATED_YET",
                        },
                    },
                    {"name": "BR Damage", "value": 402311, "key": "damage"},
                    {"name": None, "value": None, "key": None},
                ],
            }
        },
    }
    snapshot = parse_bridge(body, Platform.PC)
    assert snapshot.trackers == {"kills": 279, "damage": 402311}


def test_parse_bridge_falls_back_to_realtime_legend_and_defaults_prestige() -> None:
    body: JsonValue = {
        "global": {"name": "P", "uid": "1", "level": 10, "toNextLevelPercent": 5},
        "realtime": {"selectedLegend": "Lifeline"},
    }
    snapshot = parse_bridge(body, Platform.X1)
    assert snapshot.selected_legend == "Lifeline"
    assert snapshot.level_prestige == 0
    assert snapshot.trackers == {}
    assert snapshot.rank_score is None


def test_parse_bridge_coerces_numeric_strings() -> None:
    body: JsonValue = {
        "global": {
            "name": "P",
            "uid": 42,
            "level": 10,
            "toNextLevelPercent": 5,
            "rank": {"rankScore": "1200", "rankDiv": 3.0, "rankName": "Gold"},
        },
        "legends": {"selected": {"LegendName": "Bangalore", "data": [{"key": "k", "value": "7"}]}},
    }
    snapshot = parse_bridge(body, Platform.PS4)
    assert snapshot.uid == "42"
    assert snapshot.rank_score == 1200
    assert snapshot.rank_div == 3
    assert snapshot.trackers == {"k": 7}


def test_parse_bridge_rejects_unexpected_shape() -> None:
    with pytest.raises(UpstreamError):
        parse_bridge({"global": {"name": "no uid or level"}}, Platform.PC)
