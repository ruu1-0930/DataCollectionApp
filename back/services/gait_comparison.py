"""Pure comparison of canonical gait-session summaries."""

from services.gait_analysis import CANONICAL_METRIC_KEYS, DERIVED_METRICS, FIRMWARE_METRICS


def _metric_unit(metric_key):
    if metric_key in FIRMWARE_METRICS:
        return FIRMWARE_METRICS[metric_key]["unit"]
    return DERIVED_METRICS[metric_key]["unit"]


def _metric_value(summary, metric_key):
    metric = summary.get("metrics", {}).get(metric_key)
    return metric.get("value") if isinstance(metric, dict) else None


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
            if value is None or baseline_value is None:
                delta_abs = None
                delta_pct = None
            else:
                delta_abs = value - baseline_value
                delta_pct = delta_abs / baseline_value * 100 if baseline_value else None
            rows.append(
                {
                    "session_id": summary["session_id"],
                    "value": value,
                    "unit": _metric_unit(metric_key),
                    "delta_abs": delta_abs,
                    "delta_pct": delta_pct,
                }
            )
        metrics[metric_key] = rows

    return {"session_ids": list(session_ids), "metrics": metrics}
