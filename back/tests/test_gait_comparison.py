import math

import pytest

from services.gait_comparison import compare_session_summaries


def summary(session_id, speed, patient_id="P1"):
    return {
        "session_id": session_id,
        "patient_id": patient_id,
        "metrics": {
            "walking_speed_mps": {"value": speed, "unit": "m/s"},
            "step_length_m": {"value": 0.6, "unit": "m"},
        },
        "data_quality": {"status": "complete"},
    }


def test_compare_preserves_requested_order_and_uses_first_as_baseline():
    summaries = [summary("S1", 0.80), summary("S2", 0.92), summary("S3", 0.86)]
    out = compare_session_summaries(summaries, ["S2", "S1"])
    speed = out["metrics"]["walking_speed_mps"]
    assert [row["session_id"] for row in speed] == ["S2", "S1"]
    assert speed[0]["delta_abs"] == 0
    assert speed[1]["delta_abs"] == pytest.approx(-0.12)


@pytest.mark.parametrize("ids", [[], ["S1"], ["S1", "S2", "S3", "S4", "S5", "S6"]])
def test_compare_requires_two_to_five_sessions(ids):
    with pytest.raises(ValueError, match="2 to 5"):
        compare_session_summaries([], ids)


def test_compare_keeps_missing_values_missing():
    out = compare_session_summaries([summary("S1", 0.8), summary("S2", None)], ["S1", "S2"])
    assert out["metrics"]["walking_speed_mps"][1]["value"] is None
    assert out["metrics"]["walking_speed_mps"][1]["delta_abs"] is None
    assert out["metrics"]["walking_speed_mps"][1]["reason"] == "value_unavailable"


@pytest.mark.parametrize("unavailable", [None, math.nan, math.inf, -math.inf])
def test_compare_treats_non_finite_values_as_unavailable(unavailable):
    out = compare_session_summaries(
        [summary("S1", 0.8), summary("S2", unavailable)],
        ["S1", "S2"],
    )

    row = out["metrics"]["walking_speed_mps"][1]
    assert row["value"] is None
    assert row["delta_abs"] is None
    assert row["delta_pct"] is None
    assert row["reason"] == "value_unavailable"


def test_compare_percentage_change_reports_zero_baseline_reason():
    out = compare_session_summaries(
        [summary("S1", 0.0), summary("S2", 0.8)],
        ["S1", "S2"],
    )

    rows = out["metrics"]["walking_speed_mps"]
    assert rows[0]["delta_abs"] == 0.0
    assert rows[0]["delta_pct"] is None
    assert rows[0]["reason"] == "baseline_zero"
    assert rows[1]["delta_abs"] == pytest.approx(0.8)
    assert rows[1]["delta_pct"] is None
    assert rows[1]["reason"] == "baseline_zero"


def test_compare_returns_separate_recent_five_valid_history_medians():
    summaries = [
        summary("S1", 0.5),
        summary("S2", 99.0),
        summary("S3", 0.0),
        summary("S4", math.nan),
        summary("S5", 0.8),
        summary("S6", 1.0),
        summary("S7", 1.2),
        summary("S8", 1.4),
        summary("S9", 1.6),
    ]
    summaries[1]["data_quality"]["status"] = "limited"

    out = compare_session_summaries(summaries, ["S1", "S2"])

    assert out["history_baselines"]["walking_speed_mps"] == {
        "median": 1.2,
        "reason": None,
    }
    assert out["metrics"]["walking_speed_mps"][0]["delta_abs"] == 0.0


def test_compare_history_uses_one_recent_five_session_set_without_backfill():
    summaries = [
        summary("S0", 999.0),
        summary("S1", 0.0),
        summary("S2", None),
        summary("S3", 2.0),
        summary("S4", 4.0),
        summary("S5", 6.0),
    ]
    for index, item in enumerate(summaries):
        item["metrics"]["step_length_m"]["value"] = 999.0 if index == 0 else index / 10

    out = compare_session_summaries(summaries, ["S4", "S5"])

    assert out["history_baselines"]["walking_speed_mps"] == {
        "median": 3.0,
        "reason": None,
    }
    assert out["history_baselines"]["step_length_m"] == {
        "median": 0.3,
        "reason": None,
    }


def test_compare_nulls_arithmetic_overflow_with_reason():
    out = compare_session_summaries(
        [summary("S1", -1e308), summary("S2", 1e308)],
        ["S1", "S2"],
    )

    row = out["metrics"]["walking_speed_mps"][1]
    assert row["delta_abs"] is None
    assert row["delta_pct"] is None
    assert row["reason"] == "arithmetic_non_finite"


def test_compare_nulls_overflowed_history_median_without_older_backfill():
    summaries = [
        summary("S0", 0.5),
        summary("S1", 1e308),
        summary("S2", None),
        summary("S3", 1e308),
        summary("S4", 1e308),
        summary("S5", 1e308),
    ]

    out = compare_session_summaries(summaries, ["S4", "S5"])

    assert out["history_baselines"]["walking_speed_mps"] == {
        "median": None,
        "reason": "arithmetic_non_finite",
    }


def test_compare_rejects_summaries_from_different_patients():
    summaries = [summary("S1", 0.8, "P1"), summary("S2", 0.9, "P2")]
    with pytest.raises(ValueError, match="same patient"):
        compare_session_summaries(summaries, ["S1", "S2"])


def test_compare_rejects_when_all_patient_ids_are_missing():
    summaries = [summary("S1", 0.8), summary("S2", 0.9)]
    for item in summaries:
        item.pop("patient_id")
    with pytest.raises(ValueError, match="patient_id"):
        compare_session_summaries(summaries, ["S1", "S2"])


def test_compare_rejects_when_any_patient_id_is_missing():
    summaries = [summary("S1", 0.8), summary("S2", 0.9)]
    summaries[1].pop("patient_id")
    with pytest.raises(ValueError, match="patient_id"):
        compare_session_summaries(summaries, ["S1", "S2"])


@pytest.mark.parametrize("patient_id", [None, "", "   "])
def test_compare_rejects_empty_patient_id(patient_id):
    summaries = [summary("S1", 0.8), summary("S2", 0.9, patient_id)]
    with pytest.raises(ValueError, match="patient_id"):
        compare_session_summaries(summaries, ["S1", "S2"])


def test_compare_rejects_missing_requested_session_id():
    with pytest.raises(ValueError, match="missing requested session"):
        compare_session_summaries([summary("S1", 0.8)], ["S1", "S2"])


def test_compare_rejects_duplicate_summary_session_ids():
    summaries = [summary("S1", 0.8), summary("S1", 0.9), summary("S2", 1.0)]
    with pytest.raises(ValueError, match="summary session_ids must be unique"):
        compare_session_summaries(summaries, ["S1", "S2"])
