"""Sensor chart values belong to the frozen B snapshot, not UI calculations."""

from copy import deepcopy
from datetime import timedelta
import sys

import pytest

from services.snapshot_pipeline import SnapshotPipeline, _chart_dto
from .test_snapshot_pipeline import T0, revision, rows


def sensor_rows():
    source = rows()
    for row in source:
        row.update({f"p{i}": (9.0 if row["foot"] == "L" else 18.0) for i in range(1, 10)})
        row.update(ax=0.0, ay=3.0, az=4.0, gx=99999.0, gy=-99999.0, gz=None)
        if row["foot"] == "L":
            row["p1"] = 0.0  # 8*9/9=8; zero is not missing in a frame trend.
        else:
            row.update(ax=6.0, ay=8.0, az=0.0)
    return source


def test_sensor_charts_use_nine_point_means_and_bilateral_acceleration_only():
    source = sensor_rows()
    original = deepcopy(source)
    result = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    for point in result.full_snapshot["chart_series"]:
        assert point["pressure_left_adc_decimal"] == "8.000000"
        assert point["pressure_right_adc_decimal"] == "18.000000"
        assert point["imu_magnitude_raw_unscaled_decimal"] == "7.500000"
    assert source == original
    assert result.full_snapshot["metrics"][0]["value_decimal"] == "1.200000"
    assert "chart_series" not in result.agent_projection
    assert result.agent_projection["snapshot_content_hash"] == result.full_snapshot["content_hash"]


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf"), -1.0])
def test_incomplete_or_invalid_pressure_point_is_gap_not_partial_average(invalid):
    source = sensor_rows()
    source[0]["p9"] = invalid
    result = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    first, second = result.full_snapshot["chart_series"]
    assert first["pressure_left_adc_decimal"] is None
    assert first["pressure_right_adc_decimal"] == "18.000000"
    assert first["imu_magnitude_raw_unscaled_decimal"] == "7.500000"
    assert second["pressure_left_adc_decimal"] == "8.000000"
    assert result.full_snapshot["analyzer_statuses"]["chart"] == "success"


@pytest.mark.parametrize("axis,invalid", [("ax", None), ("az", float("inf")), ("ay", 1.7e308)])
def test_missing_or_unrepresentable_acceleration_is_gap_without_discarding_pressure(axis, invalid):
    source = sensor_rows()
    source[0][axis] = invalid
    result = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    first, second = result.full_snapshot["chart_series"]
    assert first["imu_magnitude_raw_unscaled_decimal"] is None
    assert first["pressure_left_adc_decimal"] == "8.000000"
    assert second["imu_magnitude_raw_unscaled_decimal"] == "7.500000"
    assert result.full_snapshot["analyzer_statuses"]["chart"] == "success"


def test_unpaired_frame_withholds_bilateral_imu_but_keeps_present_pressure():
    source = sensor_rows()
    source[1]["foot"] = "X"
    result = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    first = result.full_snapshot["chart_series"][0]
    assert first["pressure_left_adc_decimal"] == "8.000000"
    assert first["pressure_right_adc_decimal"] is None
    assert first["imu_magnitude_raw_unscaled_decimal"] is None


def test_maximum_finite_pressure_withholds_one_value_without_losing_other_chart_points():
    source = sensor_rows()
    source[0].update({f"p{i}": sys.float_info.max for i in range(1, 10)})
    result = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    first, second = result.full_snapshot["chart_series"]
    assert first["pressure_left_adc_decimal"] is None
    assert first["pressure_right_adc_decimal"] == "18.000000"
    assert first["imu_magnitude_raw_unscaled_decimal"] == "7.500000"
    assert second["pressure_left_adc_decimal"] == "8.000000"
    assert result.full_snapshot["analyzer_statuses"]["chart"] == "success"


def test_zero_sensor_values_remain_zero_and_chart_limit_remains_first_500():
    source = sensor_rows()
    for row in source:
        row.update({f"p{i}": 0.0 for i in range(1, 10)})
        row.update(ax=0.0, ay=0.0, az=0.0)
    frames = [{"collected_at": T0 + timedelta(milliseconds=i), "L": source[0], "R": source[1]}
              for i in range(501)]
    chart = _chart_dto(frames)
    assert len(chart) == 500
    assert chart[-1]["t_ms"] == 499
    assert chart[0]["pressure_left_adc_decimal"] == "0.000000"
    assert chart[0]["imu_magnitude_raw_unscaled_decimal"] == "0.000000"
