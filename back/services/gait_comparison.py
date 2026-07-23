"""Pure comparison of canonical gait-session summaries."""

import statistics

from services.gait_analysis import (
    CANONICAL_METRIC_KEYS,
    DERIVED_METRICS,
    FIRMWARE_METRICS,
    _finite_or_none,
)


def _metric_unit(metric_key):
    if metric_key in FIRMWARE_METRICS:
        return FIRMWARE_METRICS[metric_key]["unit"]
    return DERIVED_METRICS[metric_key]["unit"]


def _metric_value(summary, metric_key):
    metric = summary.get("metrics", {}).get(metric_key)
    return _finite_or_none(metric.get("value")) if isinstance(metric, dict) else None


def _history_baseline(summaries, metric_key):
    values = [
        value
        for summary in summaries
        if summary.get("data_quality", {}).get("status") in {"complete", "usable"}
        if (value := _metric_value(summary, metric_key)) not in (None, 0)
    ][-5:]
    if not values:
        return {"median": None, "reason": "history_insufficient"}
    return {"median": statistics.median(values), "reason": None}


def _delta(value, baseline_value):
    if value is None:
        return None, None, "value_unavailable"
    if baseline_value is None:
        return None, None, "baseline_unavailable"

    delta_abs = value - baseline_value
    if baseline_value == 0:
        return delta_abs, None, "baseline_zero"
    return delta_abs, delta_abs / baseline_value * 100, None


def compare_session_summaries(summaries, session_ids):
    """Compare two to five requested summaries against the first requested session."""
    if not 2 <= len(session_ids) <= 5:
        raise ValueError("comparison requires 2 to 5 sessions")
    if len(set(session_ids)) != len(session_ids):
        raise ValueError("session_ids must be unique")

    summary_ids = [summary.get("session_id") for summary in summaries]
    if len(set(summary_ids)) != len(summary_ids):
        raise ValueError("summary session_ids must be unique")

    summaries_by_id = {summary.get("session_id"): summary for summary in summaries}
    missing_ids = [session_id for session_id in session_ids if session_id not in summaries_by_id]
    if missing_ids:
        raise ValueError(f"missing requested session summaries: {missing_ids}")
    selected = [summaries_by_id[session_id] for session_id in session_ids]
    patient_ids = [summary.get("patient_id") for summary in selected]
    if any(
        patient_id is None
        or (isinstance(patient_id, str) and not patient_id.strip())
        for patient_id in patient_ids
    ):
        raise ValueError("selected summaries require a non-empty patient_id")
    if len(set(patient_ids)) != 1:
        raise ValueError("selected summaries must belong to the same patient")

    metrics = {}
    for metric_key in CANONICAL_METRIC_KEYS:
        baseline_value = _metric_value(selected[0], metric_key)
        rows = []
        for summary in selected:
            value = _metric_value(summary, metric_key)
            delta_abs, delta_pct, reason = _delta(value, baseline_value)
            rows.append(
                {
                    "session_id": summary["session_id"],
                    "value": value,
                    "unit": _metric_unit(metric_key),
                    "delta_abs": delta_abs,
                    "delta_pct": delta_pct,
                    "reason": reason,
                }
            )
        metrics[metric_key] = rows

    history_baselines = {
        metric_key: _history_baseline(summaries, metric_key)
        for metric_key in CANONICAL_METRIC_KEYS
    }
    return {
        "session_ids": list(session_ids),
        "metrics": metrics,
        "history_baselines": history_baselines,
    }
