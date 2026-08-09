from copy import deepcopy
from datetime import datetime
import math

import pytest

from services.pressure_analysis import pressure_attention_level, summarize_pressure


SENSOR_KEYS = tuple(f"p{index}" for index in range(1, 10))


def frame(*, left=None, right=None):
    return {
        "collected_at": datetime(2026, 7, 25, 10, 0, 0),
        "L": left,
        "R": right,
    }


def sensor_row(keys, value):
    return {key: value for key in keys}


def assert_summary_numbers_are_finite(value):
    if isinstance(value, dict):
        for item in value.values():
            assert_summary_numbers_are_finite(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            assert_summary_numbers_are_finite(item)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        assert math.isfinite(value)


def test_nonzero_mean_is_per_side_and_sensor():
    frames = [
        frame(left={"p1": 0.0, "p2": 10.0}, right={"p1": 20.0, "p2": 30.0}),
        frame(left={"p1": 10.0, "p2": 20.0}, right={"p1": 40.0, "p2": 0.0}),
    ]

    summary = summarize_pressure(frames)

    assert summary["left"]["sensors"]["p1"] == {
        "mean_adc": 10.0,
        "valid_samples": 1,
        "total_samples": 2,
    }
    assert summary["right"]["sensors"]["p1"]["mean_adc"] == 30.0
    assert summary["left"]["sensors"]["p2"]["mean_adc"] == 15.0
    assert summary["right"]["sensors"]["p2"]["mean_adc"] == 30.0


def test_all_zero_and_nonfinite_values_become_unavailable():
    summary = summarize_pressure(
        [frame(left={"p1": 0.0}, right={"p1": float("nan")})]
    )

    assert summary["left"]["sensors"]["p1"]["mean_adc"] is None
    assert summary["right"]["sensors"]["p1"]["mean_adc"] is None
    assert summary["attention"]["quality"] == "insufficient"
    assert summary["attention"]["level"] is None


def test_sensor_statistics_exclude_bool_none_string_nonfinite_and_nonpositive_values():
    values = [True, None, "12", float("nan"), float("inf"), -float("inf"), 0, -4, 12.0]
    frames = [frame(left={"p1": value}) for value in values]

    statistics = summarize_pressure(frames)["left"]["sensors"]["p1"]

    assert statistics == {
        "mean_adc": 12.0,
        "valid_samples": 1,
        "total_samples": 9,
    }


def test_huge_integer_that_cannot_convert_to_float_is_unavailable_without_raising():
    summary = summarize_pressure([frame(left={"p1": 10**400})])

    assert summary["left"]["sensors"]["p1"] == {
        "mean_adc": None,
        "valid_samples": 0,
        "total_samples": 1,
    }
    assert_summary_numbers_are_finite(summary)


def test_scaled_positive_mean_stays_finite_for_repeated_near_max_values():
    frames = [frame(left={"p1": 1.7e308}) for _ in range(3)]

    summary = summarize_pressure(frames)

    assert summary["left"]["sensors"]["p1"] == {
        "mean_adc": 1.7e308,
        "valid_samples": 3,
        "total_samples": 3,
    }
    assert_summary_numbers_are_finite(summary)


def test_total_samples_count_only_rows_where_that_foot_is_present():
    frames = [
        frame(left={"p1": 10.0}),
        frame(right={"p1": 20.0}),
        frame(left={"p1": 30.0}, right={"p1": 40.0}),
        frame(left={"p1": 50.0}),
    ]

    summary = summarize_pressure(frames)

    assert summary["left"]["sensors"]["p1"]["total_samples"] == 3
    assert summary["right"]["sensors"]["p1"]["total_samples"] == 2
    assert summary["left"]["sensors"]["p9"]["total_samples"] == 3
    assert summary["right"]["sensors"]["p9"]["total_samples"] == 2


def test_summary_always_contains_all_nine_sensors_per_side_and_contract_metadata():
    summary = summarize_pressure([])

    assert summary["method"] == "nonzero_mean_v1"
    assert summary["unit"] == "ADC"
    assert summary["threshold_profile"] == "pressure_asymmetry_research_v1"
    assert tuple(summary["left"]["sensors"]) == SENSOR_KEYS
    assert tuple(summary["right"]["sensors"]) == SENSOR_KEYS
    assert summary["left"]["sensors"]["p9"] == {
        "mean_adc": None,
        "valid_samples": 0,
        "total_samples": 0,
    }


def test_matched_sensor_requires_means_and_three_valid_samples_on_both_sides():
    frames = [
        frame(left={"p1": 10.0}, right={"p1": 20.0}),
        frame(left={"p1": 10.0}, right={"p1": 20.0}),
        frame(left={"p1": 10.0}, right={"p1": 0.0}),
    ]

    summary = summarize_pressure(frames)

    assert summary["left"]["sensors"]["p1"]["mean_adc"] == 10.0
    assert summary["right"]["sensors"]["p1"]["mean_adc"] == 20.0
    assert summary["bilateral"]["matched_sensor_count"] == 0
    assert summary["bilateral"]["sensors"] == {}
    assert summary["attention"] == {
        "level": None,
        "quality": "insufficient",
        "reason_codes": ["insufficient_pressure_data"],
    }


def test_load_proxy_uses_only_the_same_matched_sensor_set():
    frames = [
        frame(left={"p1": 10.0, "p2": 1000.0}, right={"p1": 20.0, "p2": 2000.0}),
        frame(left={"p1": 10.0, "p2": 1000.0}, right={"p1": 20.0, "p2": 2000.0}),
        frame(left={"p1": 10.0, "p2": 1000.0}, right={"p1": 20.0, "p2": 0.0}),
    ]

    summary = summarize_pressure(frames)
    bilateral = summary["bilateral"]

    assert bilateral["matched_sensor_count"] == 1
    assert tuple(bilateral["sensors"]) == ("p1",)
    assert bilateral["left_load_proxy_adc"] == 10.0
    assert bilateral["right_load_proxy_adc"] == 20.0
    assert bilateral["left_load_share_pct"] == pytest.approx(100 / 3)
    assert bilateral["right_load_share_pct"] == pytest.approx(200 / 3)
    assert bilateral["load_asymmetry_pct"] == pytest.approx(200 / 3)
    assert summary["attention"]["quality"] == "partial"
    assert summary["attention"]["level"] is None


def test_scaled_positive_asymmetry_and_shares_avoid_intermediate_overflow():
    frames = [
        frame(left={"p1": 1.7e308}, right={"p1": 1.6e308})
        for _ in range(3)
    ]

    summary = summarize_pressure(frames)
    bilateral = summary["bilateral"]

    assert bilateral["left_load_proxy_adc"] == 1.7e308
    assert bilateral["right_load_proxy_adc"] == 1.6e308
    assert bilateral["left_load_share_pct"] == pytest.approx(1700 / 33)
    assert bilateral["right_load_share_pct"] == pytest.approx(1600 / 33)
    assert bilateral["load_asymmetry_pct"] == pytest.approx(200 / 33)
    assert bilateral["sensors"]["p1"]["asymmetry_pct"] == pytest.approx(200 / 33)
    assert_summary_numbers_are_finite(summary)


def test_unrepresentable_matched_load_proxies_degrade_attention_conservatively():
    keys = SENSOR_KEYS[:6]
    frames = [
        frame(left=sensor_row(keys, 3e307), right=sensor_row(keys, 3e307))
        for _ in range(3)
    ]

    summary = summarize_pressure(frames)
    bilateral = summary["bilateral"]

    assert bilateral["matched_sensor_count"] == 6
    assert bilateral["left_load_proxy_adc"] is None
    assert bilateral["right_load_proxy_adc"] is None
    assert bilateral["left_load_share_pct"] is None
    assert bilateral["right_load_share_pct"] is None
    assert bilateral["load_asymmetry_pct"] is None
    assert summary["attention"] == {
        "level": None,
        "quality": "insufficient",
        "reason_codes": ["insufficient_pressure_data"],
    }
    assert_summary_numbers_are_finite(summary)


def test_exactly_six_matched_sensors_are_usable_with_deterministic_reasons():
    keys = SENSOR_KEYS[:6]
    frames = [
        frame(
            left={**sensor_row(keys, 100.0), "p1": 120.0},
            right=sensor_row(keys, 100.0),
        )
        for _ in range(3)
    ]

    summary = summarize_pressure(frames)

    assert summary["bilateral"]["matched_sensor_count"] == 6
    assert summary["bilateral"]["sensors"]["p1"] == {
        "difference_adc": 20.0,
        "asymmetry_pct": pytest.approx(200 / 11),
        "higher_side": "left",
    }
    assert summary["attention"] == {
        "level": "mild",
        "quality": "usable",
        "reason_codes": ["left_load_higher", "sensor_asymmetry"],
    }


def test_five_matched_sensors_are_partial_and_do_not_emit_level():
    keys = SENSOR_KEYS[:5]
    frames = [
        frame(left=sensor_row(keys, 200.0), right=sensor_row(keys, 100.0))
        for _ in range(3)
    ]

    attention = summarize_pressure(frames)["attention"]

    assert attention == {
        "level": None,
        "quality": "partial",
        "reason_codes": [
            "left_load_higher",
            "sensor_asymmetry",
            "partial_sensor_coverage",
        ],
    }


def test_missing_foot_is_insufficient_even_when_other_foot_has_valid_samples():
    frames = [frame(right=sensor_row(SENSOR_KEYS, 100.0)) for _ in range(3)]

    summary = summarize_pressure(frames)

    assert summary["bilateral"]["matched_sensor_count"] == 0
    assert summary["bilateral"]["left_load_proxy_adc"] is None
    assert summary["bilateral"]["right_load_proxy_adc"] is None
    assert summary["attention"] == {
        "level": None,
        "quality": "insufficient",
        "reason_codes": ["insufficient_pressure_data"],
    }


def test_equal_usable_loads_have_zero_difference_and_no_reason_codes():
    keys = SENSOR_KEYS[:6]
    frames = [
        frame(left=sensor_row(keys, 100.0), right=sensor_row(keys, 100.0))
        for _ in range(3)
    ]

    summary = summarize_pressure(frames)
    bilateral = summary["bilateral"]

    assert bilateral["left_load_share_pct"] == 50.0
    assert bilateral["right_load_share_pct"] == 50.0
    assert bilateral["load_asymmetry_pct"] == 0.0
    assert bilateral["sensors"]["p1"] == {
        "difference_adc": 0.0,
        "asymmetry_pct": 0.0,
        "higher_side": None,
    }
    assert summary["attention"] == {
        "level": "normal",
        "quality": "usable",
        "reason_codes": [],
    }


def test_right_higher_reason_precedes_sensor_asymmetry():
    keys = SENSOR_KEYS[:6]
    frames = [
        frame(left=sensor_row(keys, 100.0), right=sensor_row(keys, 200.0))
        for _ in range(3)
    ]

    assert summarize_pressure(frames)["attention"]["reason_codes"] == [
        "right_load_higher",
        "sensor_asymmetry",
    ]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (9.999, "normal"),
        (10.0, "mild"),
        (19.999, "mild"),
        (20.0, "moderate"),
        (29.999, "moderate"),
        (30.0, "high"),
    ],
)
def test_attention_boundaries(value, expected):
    assert pressure_attention_level(value) == expected


def test_summarize_pressure_does_not_mutate_input_frames():
    frames = [
        frame(left={"p1": 10.0, "note": "keep"}, right={"p1": 20.0}),
        frame(left=None, right={"p1": 30.0}),
    ]
    original = deepcopy(frames)

    summarize_pressure(frames)

    assert frames == original
