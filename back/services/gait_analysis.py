"""Pure functions for auditable gait-session aggregation."""

import statistics

from services.gait_thresholds import CLINICAL_REFERENCE_RULE, EXPLORATORY_FLAG_RULES


FIRMWARE_METRICS = {
    "walking_speed_mps": {"field": "walking_speed", "unit": "m/s"},
    "step_length_m": {"field": "step_length", "unit": "m"},
    "single_support_time_s": {"field": "single_support_time", "unit": "s"},
    "double_support_time_s": {"field": "double_support_time", "unit": "s"},
}

CANONICAL_METRIC_KEYS = (
    "walking_speed_mps",
    "step_length_m",
    "single_support_time_s",
    "double_support_time_s",
    "cadence_spm",
    "step_length_asymmetry_pct",
    "stride_time_cv_pct",
    "double_support_ratio_pct",
)

DERIVED_METRICS = {
    "cadence_spm": {
        "unit": "steps/min",
        "formula": "walking_speed_mps / step_length_m * 60",
    },
    "step_length_asymmetry_pct": {
        "unit": "%",
        "formula": "abs(left_step_length_m - right_step_length_m) / ((left_step_length_m + right_step_length_m) / 2) * 100",
    },
    "stride_time_cv_pct": {
        "unit": "%",
        "formula": "std(step_length_m / walking_speed_mps) / mean(step_length_m / walking_speed_mps) * 100",
    },
    "double_support_ratio_pct": {
        "unit": "%",
        "formula": "double_support_time_s / (single_support_time_s + double_support_time_s) * 100",
    },
}

REQUIRED_FIRMWARE_FIELDS = tuple(spec["field"] for spec in FIRMWARE_METRICS.values())


def segment_sessions(rows, gap_seconds=30):
    """Group ordered device rows into timestamp-paired left/right frames."""
    if not rows:
        return []

    ordered = sorted(rows, key=lambda row: row["collected_at"])
    groups = [[ordered[0]]]
    for previous, current in zip(ordered, ordered[1:]):
        gap = abs((current["collected_at"] - previous["collected_at"]).total_seconds())
        if gap > gap_seconds:
            groups.append([current])
        else:
            groups[-1].append(current)

    return [_build_session(index, group) for index, group in enumerate(groups)]


def _build_session(index, rows):
    frames = {}
    timestamps = []
    for row in rows:
        timestamp = row["collected_at"]
        if timestamp not in frames:
            frames[timestamp] = {"collected_at": timestamp, "L": None, "R": None}
            timestamps.append(timestamp)
        frames[timestamp][row["foot"]] = row

    return {
        "session_index": index,
        "start": timestamps[0],
        "end": timestamps[-1],
        "frame_count": len(timestamps),
        "frames": [frames[timestamp] for timestamp in timestamps],
    }


def _frame_value(frame, field):
    values = [
        frame[foot][field]
        for foot in ("L", "R")
        if frame.get(foot) is not None and frame[foot].get(field) is not None
    ]
    return statistics.fmean(values) if values else None


def _frame_series(frames, field):
    return [value for frame in frames if (value := _frame_value(frame, field)) is not None]


def _side_mean(frames, foot, field):
    values = [
        frame[foot][field]
        for frame in frames
        if frame.get(foot) is not None and frame[foot].get(field) is not None
    ]
    return statistics.fmean(values) if values else None


def _statistics(values):
    if not values:
        return {"mean": None, "median": None, "std": None, "cv_pct": None, "n": 0}

    mean = statistics.fmean(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean,
        "median": statistics.median(values),
        "std": std,
        "cv_pct": (std / mean * 100) if mean else 0.0,
        "n": len(values),
    }


def _metric(value_series, unit, source, formula, left_value=None, right_value=None):
    stats = _statistics(value_series)
    return {
        "value": stats["mean"],
        "unit": unit,
        "source": source,
        "formula": formula,
        "left_value": left_value,
        "right_value": right_value,
        "statistics": stats,
        "quality_notes": [],
    }


def _ratio_series(frames, numerator_field, denominator_field, multiplier=1):
    values = []
    for frame in frames:
        numerator = _frame_value(frame, numerator_field)
        denominator = _frame_value(frame, denominator_field)
        if numerator is not None and denominator not in (None, 0):
            values.append(numerator / denominator * multiplier)
    return values


def aggregate_session(frames):
    """Aggregate firmware values and transparent derived metrics without imputation."""
    metrics = {}
    for key, spec in FIRMWARE_METRICS.items():
        field = spec["field"]
        metrics[key] = _metric(
            _frame_series(frames, field),
            spec["unit"],
            "firmware",
            None,
            _side_mean(frames, "L", field),
            _side_mean(frames, "R", field),
        )

    cadence_values = _ratio_series(frames, "walking_speed", "step_length", multiplier=60)
    cadence_left = _safe_ratio(
        metrics["walking_speed_mps"]["left_value"],
        metrics["step_length_m"]["left_value"],
        multiplier=60,
    )
    cadence_right = _safe_ratio(
        metrics["walking_speed_mps"]["right_value"],
        metrics["step_length_m"]["right_value"],
        multiplier=60,
    )
    metrics["cadence_spm"] = _metric(
        cadence_values,
        DERIVED_METRICS["cadence_spm"]["unit"],
        "derived",
        DERIVED_METRICS["cadence_spm"]["formula"],
        cadence_left,
        cadence_right,
    )

    left_step = metrics["step_length_m"]["left_value"]
    right_step = metrics["step_length_m"]["right_value"]
    asymmetry = None
    if left_step is not None and right_step is not None and left_step + right_step:
        asymmetry = abs(left_step - right_step) / ((left_step + right_step) / 2) * 100
    metrics["step_length_asymmetry_pct"] = _metric(
        [] if asymmetry is None else [asymmetry],
        DERIVED_METRICS["step_length_asymmetry_pct"]["unit"],
        "derived",
        DERIVED_METRICS["step_length_asymmetry_pct"]["formula"],
    )

    stride_time_values = _ratio_series(frames, "step_length", "walking_speed")
    stride_time_stats = _statistics(stride_time_values)
    stride_time_cv = stride_time_stats["cv_pct"]
    metrics["stride_time_cv_pct"] = _metric(
        [] if stride_time_cv is None else [stride_time_cv],
        DERIVED_METRICS["stride_time_cv_pct"]["unit"],
        "derived",
        DERIVED_METRICS["stride_time_cv_pct"]["formula"],
    )

    double_support_values = []
    for frame in frames:
        single_support = _frame_value(frame, "single_support_time")
        double_support = _frame_value(frame, "double_support_time")
        if single_support is not None and double_support is not None:
            total_support = single_support + double_support
            if total_support:
                double_support_values.append(double_support / total_support * 100)
    metrics["double_support_ratio_pct"] = _metric(
        double_support_values,
        DERIVED_METRICS["double_support_ratio_pct"]["unit"],
        "derived",
        DERIVED_METRICS["double_support_ratio_pct"]["formula"],
    )

    return {"frame_count": len(frames), "metrics": metrics}


def _safe_ratio(numerator, denominator, multiplier=1):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * multiplier


def session_data_quality(frames):
    """Describe pairing and required-firmware completeness without changing raw data."""
    total_frames = len(frames)
    paired_frames = sum(
        1 for frame in frames if frame.get("L") is not None and frame.get("R") is not None
    )
    missing_required_values = 0
    for frame in frames:
        for foot in ("L", "R"):
            row = frame.get(foot)
            for field in REQUIRED_FIRMWARE_FIELDS:
                if row is None or row.get(field) is None:
                    missing_required_values += 1

    paired_frame_rate = paired_frames / total_frames * 100 if total_frames else 0.0
    if total_frames and paired_frames == total_frames and missing_required_values == 0:
        status = "complete"
    elif paired_frame_rate >= 80:
        status = "usable"
    else:
        status = "limited"

    return {
        "total_frames": total_frames,
        "paired_frames": paired_frames,
        "paired_frame_rate_pct": paired_frame_rate,
        "missing_required_values": missing_required_values,
        "status": status,
    }


def _metric_value(metrics, metric_key):
    metric = metrics.get(metric_key)
    return metric.get("value") if isinstance(metric, dict) else None


def _history_for_metric(history_baseline, metric_key, current_value):
    eligible_summaries = [
        summary
        for summary in (history_baseline or [])
        if summary.get("data_quality", {}).get("status") != "limited"
    ][-5:]
    prior_values = [
        value
        for summary in eligible_summaries
        if (value := _metric_value(summary.get("metrics", {}), metric_key)) is not None
    ]
    if not prior_values:
        return {"median": None, "delta_abs": None, "reason": "history_insufficient"}

    median = statistics.median(prior_values)
    return {
        "median": median,
        "delta_abs": current_value - median if current_value is not None else None,
        "reason": None,
    }


def _speed_flag(value):
    if value is None:
        return "unknown", "数据缺失"
    if value <= CLINICAL_REFERENCE_RULE["severe_max"]:
        return "attention", "明显低于筛查参考"
    if value < CLINICAL_REFERENCE_RULE["normal_min"]:
        return "attention", "低于 AWGS 2019 筛查参考"
    return "normal", "达到 AWGS 2019 筛查参考"


def _exploratory_flag(metric_key, value):
    rule = EXPLORATORY_FLAG_RULES[metric_key]
    if value is None:
        status = "unknown"
    elif rule["direction"] == "higher_worse":
        status = "attention" if value > rule["attention_above"] else "normal"
    else:
        status = "attention" if value < rule["low"] or value > rule["high"] else "normal"
    return status, f"{rule['message']}；待固件/临床验证"


def build_session_flags(metrics, history_baseline=None):
    """Return non-diagnostic evidence flags for a canonical metric mapping."""
    flags = []
    for metric_key in CANONICAL_METRIC_KEYS:
        value = _metric_value(metrics, metric_key)
        if metric_key == "walking_speed_mps":
            status, message = _speed_flag(value)
            evidence_level = "clinical_reference"
        elif metric_key in EXPLORATORY_FLAG_RULES:
            status, message = _exploratory_flag(metric_key, value)
            evidence_level = "exploratory"
        else:
            status, message, evidence_level = "normal", "仅作固件测量记录", "firmware_measurement"

        flags.append(
            {
                "metric_key": metric_key,
                "value": value,
                "status": status,
                "evidence_level": evidence_level,
                "message": message,
                "history": _history_for_metric(history_baseline, metric_key, value),
            }
        )
    return flags
