from datetime import datetime, timedelta
import math

import pytest

from services.gait_analysis import (
    _ratio_series,
    aggregate_session,
    build_session_flags,
    segment_sessions,
    session_data_quality,
)


T0 = datetime(2026, 6, 28, 10, 0, 0)


def row(ts, foot, **overrides):
    base = {
        "id": 0,
        "collected_at": ts,
        "foot": foot,
        "step_length": 0.6,
        "walking_speed": 1.1,
        "single_support_time": 0.4,
        "double_support_time": 0.2,
    }
    base.update(overrides)
    return base


def paired_frame(ts=T0, **overrides):
    return {
        "collected_at": ts,
        "L": row(ts, "L", **overrides),
        "R": row(ts, "R", **overrides),
    }


def left_only_frame(ts=T0, **overrides):
    return {"collected_at": ts, "L": row(ts, "L", **overrides), "R": None}


def metric_fixture(**values):
    defaults = {
        "walking_speed_mps": 1.1,
        "step_length_m": 0.6,
        "single_support_time_s": 0.4,
        "double_support_time_s": 0.2,
        "cadence_spm": 110.0,
        "step_length_asymmetry_pct": 5.0,
        "stride_time_cv_pct": 2.0,
        "double_support_ratio_pct": 25.0,
    }
    defaults.update(values)
    return {key: {"value": value} for key, value in defaults.items()}


# ---------- segment_sessions ----------


def test_segment_empty_returns_empty():
    assert segment_sessions([]) == []


def test_segment_pairs_left_and_right_by_timestamp():
    sessions = segment_sessions([row(T0, "L"), row(T0, "R")], gap_seconds=30)
    frame = sessions[0]["frames"][0]
    assert frame["L"]["foot"] == "L"
    assert frame["R"]["foot"] == "R"


def test_segment_pairs_duplicate_timestamp_rows_by_per_foot_ordinal():
    rows = [
        row(T0, "L", id=10, step_length=0.51),
        row(T0, "R", id=11, step_length=0.61),
        row(T0, "L", id=12, step_length=0.52),
        row(T0, "L", id=13, step_length=0.53),
        row(T0, "R", id=14, step_length=0.62),
    ]

    frames = segment_sessions(rows, gap_seconds=30)[0]["frames"]

    assert [frame["L"]["step_length"] if frame["L"] else None for frame in frames] == [
        0.51, 0.52, 0.53
    ]
    assert [frame["R"]["step_length"] if frame["R"] else None for frame in frames] == [
        0.61, 0.62, None
    ]


def test_segment_gap_splits_sessions():
    rows = [
        row(T0, "L"),
        row(T0, "R"),
        row(T0 + timedelta(seconds=60), "L"),
        row(T0 + timedelta(seconds=60), "R"),
    ]
    assert len(segment_sessions(rows, gap_seconds=30)) == 2


# ---------- aggregate_session ----------


def test_aggregate_uses_step_length_not_stride_length():
    out = aggregate_session([paired_frame(step_length=0.58, walking_speed=0.92)])
    assert "step_length_m" in out["metrics"]
    assert "stride_length" not in out["metrics"]
    assert out["metrics"]["step_length_m"]["source"] == "firmware"
    assert out["metrics"]["step_length_m"]["unit"] == "m"


def test_derived_metric_discloses_formula():
    out = aggregate_session([paired_frame(step_length=0.58, walking_speed=0.92)])
    cadence = out["metrics"]["cadence_spm"]
    assert cadence["source"] == "derived"
    assert cadence["formula"] == "walking_speed_mps / step_length_m * 60"


def test_stride_time_cv_discloses_stride_time_formula():
    out = aggregate_session([paired_frame(step_length=0.58, walking_speed=0.92)])
    stride_time_cv = out["metrics"]["stride_time_cv_pct"]
    assert stride_time_cv["formula"] == (
        "std(2 * step_length_m / walking_speed_mps) / "
        "mean(2 * step_length_m / walking_speed_mps) * 100"
    )


def test_ratio_series_supports_stride_time_factor_two():
    frames = [paired_frame(step_length=0.6, walking_speed=1.2)]
    values = _ratio_series(
        frames,
        "step_length",
        "walking_speed",
        multiplier=2,
    )
    assert values == pytest.approx([1.0])


def test_all_canonical_metrics_have_auditable_shape():
    out = aggregate_session([paired_frame(), paired_frame(T0 + timedelta(seconds=1))])
    assert set(out["metrics"]) == {
        "walking_speed_mps",
        "step_length_m",
        "single_support_time_s",
        "double_support_time_s",
        "cadence_spm",
        "step_length_asymmetry_pct",
        "stride_time_cv_pct",
        "double_support_ratio_pct",
    }
    for metric in out["metrics"].values():
        assert set(metric) == {
            "value",
            "unit",
            "source",
            "formula",
            "left_value",
            "right_value",
            "statistics",
            "quality_notes",
        }
        assert set(metric["statistics"]) == {"mean", "median", "std", "cv_pct", "n"}


def test_aggregate_never_imputes_missing_firmware_values():
    out = aggregate_session([
        paired_frame(walking_speed=None),
        left_only_frame(walking_speed=None),
    ])
    speed = out["metrics"]["walking_speed_mps"]
    assert speed["value"] is None
    assert speed["statistics"]["n"] == 0


@pytest.mark.parametrize("unavailable", [None, math.nan, math.inf, -math.inf])
def test_aggregate_treats_non_finite_firmware_values_as_missing(unavailable):
    out = aggregate_session([paired_frame(walking_speed=unavailable)])

    speed = out["metrics"]["walking_speed_mps"]
    cadence = out["metrics"]["cadence_spm"]
    assert speed["value"] is None
    assert speed["left_value"] is None
    assert speed["right_value"] is None
    assert speed["statistics"] == {
        "mean": None,
        "median": None,
        "std": None,
        "cv_pct": None,
        "n": 0,
    }
    assert cadence["value"] is None


def test_aggregate_nulls_finite_inputs_when_statistics_overflow():
    out = aggregate_session([paired_frame(walking_speed=1e308)])

    speed = out["metrics"]["walking_speed_mps"]
    cadence = out["metrics"]["cadence_spm"]
    assert speed["value"] is None
    assert speed["left_value"] == 1e308
    assert speed["right_value"] == 1e308
    assert speed["statistics"]["mean"] is None
    assert speed["statistics"]["median"] is None
    assert cadence["value"] is None


# ---------- session_data_quality ----------


def test_quality_counts_paired_and_missing_frames():
    frames = [paired_frame(), left_only_frame(), paired_frame(walking_speed=None)]
    quality = session_data_quality(frames)
    assert quality["total_frames"] == 3
    assert quality["paired_frames"] == 2
    assert quality["paired_frame_rate_pct"] == pytest.approx(66.67, abs=0.01)
    assert quality["missing_required_values"] > 0
    assert quality["status"] == "limited"


def test_quality_is_complete_only_for_fully_paired_complete_firmware_data():
    assert session_data_quality([paired_frame(), paired_frame()])["status"] == "complete"
    assert session_data_quality([paired_frame(walking_speed=None)])["status"] == "usable"


def test_quality_is_usable_at_exactly_eighty_percent_paired_frames():
    frames = [paired_frame() for _ in range(4)] + [left_only_frame()]
    quality = session_data_quality(frames)
    assert quality["paired_frame_rate_pct"] == 80.0
    assert quality["status"] == "usable"


@pytest.mark.parametrize("unavailable", [None, math.nan, math.inf, -math.inf])
def test_quality_counts_non_finite_firmware_values_as_missing(unavailable):
    quality = session_data_quality([paired_frame(walking_speed=unavailable)])

    assert quality["missing_required_values"] == 2
    assert quality["status"] == "usable"


# ---------- build_session_flags ----------


def test_only_speed_creates_clinical_reference_flag():
    metrics = metric_fixture(walking_speed_mps=0.92, step_length_asymmetry_pct=12.0)
    flags = build_session_flags(metrics)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    asymmetry = next(
        flag for flag in flags if flag["metric_key"] == "step_length_asymmetry_pct"
    )
    assert speed["evidence_level"] == "clinical_reference"
    assert speed["status"] == "attention"
    assert asymmetry["evidence_level"] == "exploratory"
    assert asymmetry["status"] == "attention"
    assert "待固件/临床验证" in asymmetry["message"]
    assert "diagnosis" not in asymmetry


def test_speed_reference_copy_uses_the_specified_boundaries():
    moderate = build_session_flags(metric_fixture(walking_speed_mps=0.92))
    severe = build_session_flags(metric_fixture(walking_speed_mps=0.8))
    moderate_speed = next(flag for flag in moderate if flag["metric_key"] == "walking_speed_mps")
    severe_speed = next(flag for flag in severe if flag["metric_key"] == "walking_speed_mps")
    assert moderate_speed["message"] == "低于 AWGS 2019 筛查参考"
    assert severe_speed["message"] == "明显低于筛查参考"


def test_history_baseline_uses_non_limited_prior_summaries_and_median():
    history = [
        {"data_quality": {"status": "complete"}, "metrics": metric_fixture(walking_speed_mps=0.2)},
        {"data_quality": {"status": "limited"}, "metrics": metric_fixture(walking_speed_mps=0.2)},
        {"data_quality": {"status": "usable"}, "metrics": metric_fixture(walking_speed_mps=0.6)},
        {"data_quality": {"status": "complete"}, "metrics": metric_fixture(walking_speed_mps=0.8)},
        {"data_quality": {"status": "usable"}, "metrics": metric_fixture(walking_speed_mps=1.0)},
        {"data_quality": {"status": "complete"}, "metrics": metric_fixture(walking_speed_mps=1.2)},
        {"data_quality": {"status": "complete"}, "metrics": metric_fixture(walking_speed_mps=1.4)},
    ]
    flags = build_session_flags(metric_fixture(walking_speed_mps=0.92), history)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    assert speed["history"]["median"] == 1.0
    assert speed["history"]["delta_abs"] == pytest.approx(-0.08)
    assert speed["history"]["delta_pct"] == pytest.approx(-8.0)
    assert speed["history"]["reason"] is None


def test_history_reports_insufficient_when_no_prior_values_exist():
    flags = build_session_flags(metric_fixture(), [])
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    assert speed["history"] == {
        "median": None,
        "delta_abs": None,
        "delta_pct": None,
        "reason": "history_insufficient",
    }


def test_history_ignores_summaries_without_explicit_quality_status():
    history = [
        {"metrics": metric_fixture(walking_speed_mps=0.2)},
        {"data_quality": {}, "metrics": metric_fixture(walking_speed_mps=0.4)},
        {
            "data_quality": {"status": "complete"},
            "metrics": metric_fixture(walking_speed_mps=1.2),
        },
    ]
    flags = build_session_flags(metric_fixture(walking_speed_mps=0.92), history)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    assert speed["history"]["median"] == 1.2
    assert speed["history"]["delta_abs"] == pytest.approx(-0.28)


def test_history_ignores_non_finite_prior_values():
    history = [
        {
            "data_quality": {"status": "complete"},
            "metrics": metric_fixture(walking_speed_mps=math.nan),
        },
        {
            "data_quality": {"status": "usable"},
            "metrics": metric_fixture(walking_speed_mps=math.inf),
        },
        {
            "data_quality": {"status": "complete"},
            "metrics": metric_fixture(walking_speed_mps=1.0),
        },
    ]

    flags = build_session_flags(metric_fixture(walking_speed_mps=1.2), history)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    assert speed["history"]["median"] == 1.0
    assert speed["history"]["delta_abs"] == pytest.approx(0.2)
    assert speed["history"]["delta_pct"] == pytest.approx(20.0)


def test_history_percentage_change_reports_zero_baseline_reason():
    history = [
        {
            "data_quality": {"status": "complete"},
            "metrics": metric_fixture(walking_speed_mps=0.0),
        }
    ]

    flags = build_session_flags(metric_fixture(walking_speed_mps=1.2), history)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")
    assert speed["history"] == {
        "median": 0.0,
        "delta_abs": 1.2,
        "delta_pct": None,
        "reason": "baseline_zero",
    }


def test_history_nulls_arithmetic_overflow_with_reason_and_unknown_delta():
    history = [
        {
            "data_quality": {"status": "complete"},
            "metrics": metric_fixture(walking_speed_mps=-1e308),
        }
    ]

    flags = build_session_flags(metric_fixture(walking_speed_mps=1e308), history)
    speed = next(flag for flag in flags if flag["metric_key"] == "walking_speed_mps")

    assert speed["history"] == {
        "median": -1e308,
        "delta_abs": None,
        "delta_pct": None,
        "reason": "arithmetic_non_finite",
    }


@pytest.mark.parametrize("unavailable", [None, math.nan, math.inf, -math.inf])
def test_flags_mark_unavailable_firmware_metrics_unknown(unavailable):
    flags = build_session_flags(metric_fixture(step_length_m=unavailable))
    step_length = next(flag for flag in flags if flag["metric_key"] == "step_length_m")

    assert step_length["value"] is None
    assert step_length["status"] == "unknown"
    assert step_length["history"]["delta_pct"] is None
