import pytest

from services.gait_comparison import compare_session_summaries


def summary(session_id, speed):
    return {
        "session_id": session_id,
        "metrics": {
            "walking_speed_mps": {"value": speed, "unit": "m/s"},
            "step_length_m": {"value": 0.6, "unit": "m"},
        },
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
