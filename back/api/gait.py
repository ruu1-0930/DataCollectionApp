"""Read-only gait workbench endpoints backed by canonical gait services."""

from datetime import datetime, timedelta
import re

from flask import Blueprint, g, jsonify, request

from config import db
from models.models import DeviceRawData, Patient
from services.gait_analysis import (
    _finite_or_none,
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
_SESSION_GAP_SECONDS = 30
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SESSION_ID_PATTERN = re.compile(
    r"^P(?P<patient_id>\d+)-(?P<timestamp>\d{8}T\d{9})$"
)
_AGGREGATE_COLS = (
    DeviceRawData.collected_at,
    DeviceRawData.foot,
    DeviceRawData.step_length,
    DeviceRawData.walking_speed,
    DeviceRawData.single_support_time,
    DeviceRawData.double_support_time,
)
_SENSOR_COLS = tuple(
    getattr(DeviceRawData, column)
    for column in _PRESSURE_COLS + _IMU_COLS
)


def _owned_patient_or_resp(patient_id):
    """Return the owned patient or the response required by ownership policy."""
    patient = Patient.query.get(patient_id)
    if not patient:
        return None, (jsonify(Response.error(404, "患者不存在")), 404)
    if patient.clinician_id != g.clinician_id:
        return None, (jsonify(Response.error(403, "无权访问该患者")), 403)
    return patient, None


def _fetch_rows(
    patient_id,
    *,
    start=None,
    end=None,
    timestamps=None,
    include_sensors=False,
):
    """Load only the requested columns and stable session/page time range."""
    columns = _AGGREGATE_COLS + (_SENSOR_COLS if include_sensors else ())
    query = db.session.query(*columns).filter(DeviceRawData.patient_id == patient_id)
    if start is not None:
        query = query.filter(DeviceRawData.collected_at >= start)
    if end is not None:
        query = query.filter(DeviceRawData.collected_at <= end)
    if timestamps is not None:
        if not timestamps:
            return []
        query = query.filter(DeviceRawData.collected_at.in_(timestamps))

    column_names = [column.key for column in columns]
    rows = []
    for values in query.order_by(DeviceRawData.collected_at.asc()).all():
        row = dict(zip(column_names, values))
        for column in column_names:
            if column not in {"collected_at", "foot"}:
                row[column] = _finite_or_none(row[column])
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


def _parse_naive_datetime(value, *, date_end=False):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError("时间必须是 ISO-8601 naive datetime")
    if parsed.tzinfo is not None:
        raise ValueError("时间不能包含时区")
    if date_end and _DATE_ONLY_PATTERN.fullmatch(value):
        return parsed + timedelta(days=1), True
    return parsed, False


def _session_filter_bounds_or_resp():
    start_value = request.args.get("start") or None
    end_value = request.args.get("end") or None
    try:
        start = _parse_naive_datetime(start_value)[0] if start_value else None
        end, end_exclusive = (
            _parse_naive_datetime(end_value, date_end=True)
            if end_value
            else (None, False)
        )
    except ValueError as error:
        return None, None, False, (jsonify(Response.error(422, str(error))), 422)
    if (
        start is not None
        and end is not None
        and (end <= start if end_exclusive else end < start)
    ):
        return None, None, False, (jsonify(Response.error(422, "end 不能早于 start")), 422)
    return start, end, end_exclusive, None


def _timestamp_query(patient_id):
    return db.session.query(DeviceRawData.collected_at).filter(
        DeviceRawData.patient_id == patient_id
    )


def _session_starts_in_range(patient_id, start, end, end_exclusive):
    effective_start = start or datetime.now() - timedelta(days=_SESSION_WINDOW_DAYS)
    previous_row = (
        _timestamp_query(patient_id)
        .filter(DeviceRawData.collected_at < effective_start)
        .distinct()
        .order_by(DeviceRawData.collected_at.desc())
        .first()
    )
    query = (
        _timestamp_query(patient_id)
        .filter(DeviceRawData.collected_at >= effective_start)
        .distinct()
    )
    if end is not None:
        operator = (
            DeviceRawData.collected_at < end
            if end_exclusive
            else DeviceRawData.collected_at <= end
        )
        query = query.filter(operator)

    timestamps = [row[0] for row in query.order_by(DeviceRawData.collected_at.asc()).all()]
    if previous_row is not None:
        timestamps.insert(0, previous_row[0])
    if not timestamps:
        return []

    starts = []
    group_start = timestamps[0]
    for previous, current in zip(timestamps, timestamps[1:]):
        if (current - previous).total_seconds() > _SESSION_GAP_SECONDS:
            if group_start >= effective_start:
                starts.append(group_start)
            group_start = current
    if group_start >= effective_start:
        starts.append(group_start)
    return starts


def _session_bounds_for_start(patient_id, start):
    previous_row = (
        _timestamp_query(patient_id)
        .filter(DeviceRawData.collected_at < start)
        .distinct()
        .order_by(DeviceRawData.collected_at.desc())
        .first()
    )
    if (
        previous_row is not None
        and (start - previous_row[0]).total_seconds() <= _SESSION_GAP_SECONDS
    ):
        return None

    previous = None
    query = (
        _timestamp_query(patient_id)
        .filter(DeviceRawData.collected_at >= start)
        .distinct()
        .order_by(DeviceRawData.collected_at.asc())
    )
    for row in query.yield_per(500):
        timestamp = row[0]
        if previous is None and timestamp != start:
            return None
        if (
            previous is not None
            and (timestamp - previous).total_seconds() > _SESSION_GAP_SECONDS
        ):
            break
        previous = timestamp
    return (start, previous) if previous is not None else None


def _parse_session_start(patient_id, session_id):
    match = _SESSION_ID_PATTERN.fullmatch(session_id)
    if match is None or int(match.group("patient_id")) != patient_id:
        return None
    try:
        start = datetime.strptime(match.group("timestamp"), "%Y%m%dT%H%M%S%f")
    except ValueError:
        return None
    return start


def _session_for_bounds(patient_id, bounds, *, include_sensors):
    rows = _fetch_rows(
        patient_id,
        start=bounds[0],
        end=bounds[1],
        include_sensors=include_sensors,
    )
    sessions = segment_sessions(rows, gap_seconds=_SESSION_GAP_SECONDS)
    if len(sessions) != 1 or sessions[0]["start"] != bounds[0]:
        return None
    return sessions[0]


def _bulk_session_records(patient_id, *, end=None):
    rows = _fetch_rows(
        patient_id,
        end=end,
        include_sensors=False,
    )
    return _session_records(rows, patient_id)


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
        "pressure": {
            column: _finite_or_none(row.get(column))
            for column in _PRESSURE_COLS
        },
        "pressure_unit": "ADC",
        "imu": {
            column: _finite_or_none(row.get(column))
            for column in _IMU_COLS
        },
        "imu_unit": "raw_unscaled",
        "walking_speed_mps": _finite_or_none(row.get("walking_speed")),
        "step_length_m": _finite_or_none(row.get("step_length")),
        "single_support_time_s": _finite_or_none(row.get("single_support_time")),
        "double_support_time_s": _finite_or_none(row.get("double_support_time")),
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

    start, end, end_exclusive, error = _session_filter_bounds_or_resp()
    if error:
        return error

    starts = _session_starts_in_range(patient_id, start, end, end_exclusive)
    if not starts:
        return jsonify(Response.success(data={"total": 0, "sessions": []}))

    final_bounds = _session_bounds_for_start(patient_id, starts[-1])
    if final_bounds is None:
        return jsonify(Response.success(data={"total": 0, "sessions": []}))
    records_by_start = {
        session["start"]: summary
        for session, summary in _bulk_session_records(
            patient_id,
            end=final_bounds[1],
        )
    }
    summaries = [
        _public_summary(records_by_start[session_start])
        for session_start in starts
        if session_start in records_by_start
    ]
    summaries.reverse()
    return jsonify(Response.success(data={"total": len(summaries), "sessions": summaries}))


@gait_bp.route("/patients/<int:patient_id>/gait/sessions/<string:session_id>", methods=["GET"])
@token_required()
def get_gait_session(patient_id, session_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    start = _parse_session_start(patient_id, session_id)
    bounds = (
        _session_bounds_for_start(patient_id, start)
        if start is not None
        else None
    )
    if bounds is None:
        return _session_not_found_response()

    record = _record_for_id(
        _bulk_session_records(patient_id, end=bounds[1]),
        session_id,
    )
    session = _session_for_bounds(patient_id, bounds, include_sensors=True)
    if record is None or session is None:
        return _session_not_found_response()

    summary = record[1]
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

    session_start = _parse_session_start(patient_id, session_id)
    bounds = (
        _session_bounds_for_start(patient_id, session_start)
        if session_start is not None
        else None
    )
    if bounds is None:
        return _session_not_found_response()

    page = _page_arg("page", 1)
    page_size = _page_arg("page_size", _PAGE_SIZE_DEFAULT, _PAGE_SIZE_MAX)
    timestamp_query = (
        _timestamp_query(patient_id)
        .filter(DeviceRawData.collected_at >= bounds[0])
        .filter(DeviceRawData.collected_at <= bounds[1])
        .distinct()
    )
    total = timestamp_query.count()
    page_timestamps = [
        row[0]
        for row in (
            timestamp_query.order_by(DeviceRawData.collected_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
    ]
    page_rows = _fetch_rows(
        patient_id,
        timestamps=page_timestamps,
        include_sensors=True,
    )
    frames = [
        frame
        for session in segment_sessions(page_rows, gap_seconds=_SESSION_GAP_SECONDS)
        for frame in session["frames"]
    ]
    items = [_frame_payload(frame) for frame in frames]
    return jsonify(
        Response.success(
            data={
                "page": page,
                "page_size": page_size,
                "total": total,
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

    if not 2 <= len(session_ids) <= 5:
        return jsonify(Response.error(422, "comparison requires 2 to 5 sessions")), 422
    if len(set(session_ids)) != len(session_ids):
        return jsonify(Response.error(422, "session_ids must be unique")), 422
    if any(_parse_session_start(patient_id, session_id) is None for session_id in session_ids):
        return jsonify(Response.error(422, "invalid session_id format")), 422

    summaries = [
        summary
        for _session, summary in _bulk_session_records(patient_id)
    ]
    try:
        data = compare_session_summaries(summaries, session_ids)
    except ValueError as error:
        return jsonify(Response.error(422, str(error))), 422
    return jsonify(Response.success(data=data))
