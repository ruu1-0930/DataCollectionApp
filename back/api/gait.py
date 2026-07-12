"""Read-only gait workbench endpoints backed by canonical gait services."""

from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request

from models.models import DeviceRawData, Patient
from services.gait_analysis import (
    aggregate_session,
    build_session_flags,
    segment_sessions,
    session_data_quality,
)
from services.gait_comparison import compare_session_summaries
from utils import Response, token_required


gait_bp = Blueprint("gait", __name__)

_PRESSURE_COLS = [f"p{index}" for index in range(1, 10)]
_IMU_COLS = ["ax", "ay", "az", "gx", "gy", "gz"]
_PAGE_SIZE_DEFAULT = 100
_PAGE_SIZE_MAX = 500
_CHART_POINT_MAX = 500
_SESSION_WINDOW_DAYS = 30


def _owned_patient_or_resp(patient_id):
    """Return the owned patient or the response required by ownership policy."""
    patient = Patient.query.get(patient_id)
    if not patient:
        return None, (jsonify(Response.error(404, "患者不存在")), 404)
    if patient.clinician_id != g.clinician_id:
        return None, (jsonify(Response.error(403, "无权访问该患者")), 403)
    return patient, None


def _fetch_rows(patient_id):
    """Load raw per-foot values only; transformed model outputs never enter the DTO."""
    query = DeviceRawData.query.filter_by(patient_id=patient_id)

    rows = []
    for raw in query.order_by(DeviceRawData.collected_at.asc()).all():
        row = {
            "collected_at": raw.collected_at,
            "foot": raw.foot,
            "step_length": raw.step_length,
            "walking_speed": raw.walking_speed,
            "single_support_time": raw.single_support_time,
            "double_support_time": raw.double_support_time,
        }
        for column in _PRESSURE_COLS + _IMU_COLS:
            row[column] = getattr(raw, column)
        rows.append(row)
    return rows


def _session_id(patient_id, start):
    milliseconds = start.microsecond // 1000
    return f"P{patient_id}-{start:%Y%m%dT%H%M%S}{milliseconds:03d}"


def _session_summary(session, patient_id, history):
    """Attach stable API identity and metadata to Task 2's canonical aggregation."""
    frames = session["frames"]
    aggregation = aggregate_session(frames)
    data_quality = session_data_quality(frames)
    summary = {
        "patient_id": patient_id,
        "session_id": _session_id(patient_id, session["start"]),
        "start": session["start"].isoformat(),
        "end": session["end"].isoformat(),
        "duration_s": (session["end"] - session["start"]).total_seconds(),
        "frame_count": aggregation["frame_count"],
        "left_frames": sum(frame.get("L") is not None for frame in frames),
        "right_frames": sum(frame.get("R") is not None for frame in frames),
        "paired_frame_rate_pct": data_quality["paired_frame_rate_pct"],
        "metrics": aggregation["metrics"],
        "data_quality": data_quality,
    }
    summary["flags"] = build_session_flags(summary["metrics"], history)
    summary["attention_count"] = sum(
        flag["status"] == "attention" for flag in summary["flags"]
    )
    return summary


def _session_records(rows, patient_id):
    """Build chronological canonical summaries so flags only see prior history."""
    history = []
    records = []
    for session in segment_sessions(rows):
        summary = _session_summary(session, patient_id, history)
        history.append(summary)
        records.append((session, summary))
    return records


def _parse_naive_datetime(value):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("时间必须是 ISO-8601 naive datetime")
    if parsed.tzinfo is not None:
        raise ValueError("时间不能包含时区")
    return parsed


def _session_filter_bounds_or_resp():
    start_value = request.args.get("start") or None
    end_value = request.args.get("end") or None
    try:
        start = _parse_naive_datetime(start_value) if start_value else None
        end = _parse_naive_datetime(end_value) if end_value else None
    except ValueError as error:
        return None, None, (jsonify(Response.error(422, str(error))), 422)
    if start is not None and end is not None and end < start:
        return None, None, (jsonify(Response.error(422, "end 不能早于 start")), 422)
    return start, end, None


def _filter_session_records(records, start, end):
    effective_start = start or datetime.now() - timedelta(days=_SESSION_WINDOW_DAYS)
    return [
        record
        for record in records
        if record[0]["start"] >= effective_start
        and (end is None or record[0]["start"] <= end)
    ]


def _public_summary(summary):
    return {key: value for key, value in summary.items() if key != "patient_id"}


def _record_for_id(records, session_id):
    for record in records:
        if record[1]["session_id"] == session_id:
            return record
    return None


def _foot_payload(row):
    if row is None:
        return None
    return {
        "pressure": {column: row.get(column) for column in _PRESSURE_COLS},
        "pressure_unit": "ADC",
        "imu": {column: row.get(column) for column in _IMU_COLS},
        "imu_unit": "raw_unscaled",
        "walking_speed_mps": row.get("walking_speed"),
        "step_length_m": row.get("step_length"),
        "single_support_time_s": row.get("single_support_time"),
        "double_support_time_s": row.get("double_support_time"),
    }


def _frame_payload(frame):
    return {
        "collected_at": frame["collected_at"].isoformat(),
        "left": _foot_payload(frame.get("L")),
        "right": _foot_payload(frame.get("R")),
    }


def _sample_frames(frames):
    if len(frames) <= _CHART_POINT_MAX:
        return frames
    last_index = len(frames) - 1
    return [
        frames[index * last_index // (_CHART_POINT_MAX - 1)]
        for index in range(_CHART_POINT_MAX)
    ]


def _chart_series(frames):
    sampled_frames = _sample_frames(frames)
    return {
        "total_points": len(frames),
        "items": [_frame_payload(frame) for frame in sampled_frames],
    }


def _page_arg(name, default, maximum=None):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        value = default
    value = max(value, 1)
    return min(value, maximum) if maximum else value


def _session_not_found_response():
    return jsonify(Response.error(404, "会话不存在")), 404


@gait_bp.route("/patients/<int:patient_id>/gait/sessions", methods=["GET"])
@token_required()
def list_gait_sessions(patient_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    start, end, error = _session_filter_bounds_or_resp()
    if error:
        return error

    records = _session_records(_fetch_rows(patient_id), patient_id)
    records = _filter_session_records(records, start, end)
    summaries = [_public_summary(summary) for _, summary in reversed(records)]
    return jsonify(Response.success(data={"total": len(summaries), "sessions": summaries}))


@gait_bp.route("/patients/<int:patient_id>/gait/sessions/<string:session_id>", methods=["GET"])
@token_required()
def get_gait_session(patient_id, session_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    record = _record_for_id(_session_records(_fetch_rows(patient_id), patient_id), session_id)
    if record is None:
        return _session_not_found_response()

    session, summary = record
    data = _public_summary(summary)
    data["chart_series"] = _chart_series(session["frames"])
    return jsonify(Response.success(data=data))


@gait_bp.route(
    "/patients/<int:patient_id>/gait/sessions/<string:session_id>/frames",
    methods=["GET"],
)
@token_required()
def get_gait_session_frames(patient_id, session_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    record = _record_for_id(_session_records(_fetch_rows(patient_id), patient_id), session_id)
    if record is None:
        return _session_not_found_response()

    page = _page_arg("page", 1)
    page_size = _page_arg("page_size", _PAGE_SIZE_DEFAULT, _PAGE_SIZE_MAX)
    frames = record[0]["frames"]
    start = (page - 1) * page_size
    items = [_frame_payload(frame) for frame in frames[start:start + page_size]]
    return jsonify(
        Response.success(
            data={
                "page": page,
                "page_size": page_size,
                "total": len(frames),
                "items": items,
            }
        )
    )


@gait_bp.route("/patients/<int:patient_id>/gait/compare", methods=["POST"])
@token_required()
def compare_gait_sessions(patient_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    payload = request.get_json(silent=True) or {}
    session_ids = payload.get("session_ids") if isinstance(payload, dict) else None
    if not isinstance(session_ids, list) or not all(isinstance(item, str) for item in session_ids):
        return jsonify(Response.error(422, "session_ids 必须是字符串数组")), 422

    summaries = [summary for _, summary in _session_records(_fetch_rows(patient_id), patient_id)]
    try:
        data = compare_session_summaries(summaries, session_ids)
    except ValueError as error:
        return jsonify(Response.error(422, str(error))), 422
    return jsonify(Response.success(data=data))
