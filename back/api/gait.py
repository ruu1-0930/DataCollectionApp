"""Read-only gait workbench endpoints backed by canonical gait services."""

from datetime import datetime, timedelta
import re

from flask import Blueprint, g, jsonify, request
from sqlalchemy import and_, case, func, or_, select

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
from services.pressure_analysis import summarize_pressure_rows
from utils import Response, token_required


gait_bp = Blueprint("gait", __name__)

_PRESSURE_COLS = [f"p{index}" for index in range(1, 10)]
_IMU_COLS = ["ax", "ay", "az", "gx", "gy", "gz"]
_PAGE_SIZE_DEFAULT = 100
_PAGE_SIZE_MAX = 500
_CHART_POINT_MAX = 500
_SESSION_WINDOW_DAYS = 30
_SESSION_GAP_SECONDS = 30
_SESSION_BOUND_CHUNK_MINUTES = 5
_SESSION_BOUND_MAX_CHUNKS = 288
_HISTORY_BATCH_SIZE = 5
_DATE_ONLY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SESSION_ID_PATTERN = re.compile(
    r"^P(?P<patient_id>\d+)-(?P<timestamp>\d{8}T\d{12})$"
)
_AGGREGATE_COLS = (
    DeviceRawData.id,
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
    ranges=None,
    foot=None,
    offset=None,
    limit=None,
    include_sensors=False,
):
    """Load only the requested columns and stable session/page time range."""
    columns = _AGGREGATE_COLS + (_SENSOR_COLS if include_sensors else ())
    query = db.session.query(*columns).filter(DeviceRawData.patient_id == patient_id)
    if start is not None:
        query = query.filter(DeviceRawData.collected_at >= start)
    if end is not None:
        query = query.filter(DeviceRawData.collected_at <= end)
    if ranges is not None:
        if not ranges:
            return []
        query = query.filter(
            or_(
                *(
                    and_(
                        DeviceRawData.collected_at >= lower,
                        DeviceRawData.collected_at <= upper,
                    )
                    for lower, upper in ranges
                )
            )
        )
    if timestamps is not None:
        if not timestamps:
            return []
        query = query.filter(DeviceRawData.collected_at.in_(timestamps))
    if foot is not None:
        query = query.filter(DeviceRawData.foot == foot)
    query = query.order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
    if offset is not None:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    column_names = [column.key for column in columns]
    rows = []
    for values in query.all():
        row = dict(zip(column_names, values))
        for column in column_names:
            if column not in {"id", "collected_at", "foot"}:
                row[column] = _finite_or_none(row[column])
        rows.append(row)
    return rows


def _fetch_pressure_rows_for_bounds(patient_id, bounds):
    """Load every raw pressure row for one resolved session in one bounded query."""
    columns = (DeviceRawData.id, DeviceRawData.foot) + tuple(
        getattr(DeviceRawData, column) for column in _PRESSURE_COLS
    )
    query = (
        db.session.query(*columns)
        .filter(DeviceRawData.patient_id == patient_id)
        .filter(DeviceRawData.collected_at >= bounds[0])
        .filter(DeviceRawData.collected_at <= bounds[1])
        .order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
    )
    column_names = [column.key for column in columns]
    rows = []
    for values in query.all():
        row = dict(zip(column_names, values))
        for column in _PRESSURE_COLS:
            row[column] = _finite_or_none(row[column])
        rows.append(row)
    return rows


def _session_id(patient_id, start):
    return f"P{patient_id}-{start:%Y%m%dT%H%M%S}{start.microsecond:06d}"


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
    return _session_bounds_for_starts(patient_id, [start]).get(start)


def _session_bounds_for_starts(patient_id, starts):
    """Resolve up to five stable session ranges with bounded batched lookahead."""
    starts = sorted(set(starts))
    if not starts:
        return {}

    gap = timedelta(seconds=_SESSION_GAP_SECONDS)
    previous_timestamps = [
        row[0]
        for row in (
            _timestamp_query(patient_id)
            .filter(
                or_(
                    *(
                        and_(
                            DeviceRawData.collected_at >= start - gap,
                            DeviceRawData.collected_at < start,
                        )
                        for start in starts
                    )
                )
            )
            .distinct()
            .all()
        )
    ]
    results = {
        start: None
        for start in starts
        if any(
            previous < start
            and (start - previous).total_seconds() <= _SESSION_GAP_SECONDS
            for previous in previous_timestamps
        )
    }
    active = {
        start: {"cursor": start, "previous": None}
        for start in starts
        if start not in results
    }
    chunk = timedelta(minutes=_SESSION_BOUND_CHUNK_MINUTES)

    for _ in range(_SESSION_BOUND_MAX_CHUNKS):
        if not active:
            break
        windows = {
            start: (state["cursor"], state["cursor"] + chunk)
            for start, state in active.items()
        }
        timestamps = [
            row[0]
            for row in (
                _timestamp_query(patient_id)
                .filter(
                    or_(
                        *(
                            and_(
                                DeviceRawData.collected_at >= lower,
                                DeviceRawData.collected_at <= upper,
                            )
                            for lower, upper in windows.values()
                        )
                    )
                )
                .distinct()
                .order_by(DeviceRawData.collected_at.asc())
                .all()
            )
        ]

        completed = []
        for start, state in active.items():
            lower, upper = windows[start]
            window_timestamps = [
                timestamp
                for timestamp in timestamps
                if lower <= timestamp <= upper
            ]
            previous = state["previous"]
            for timestamp in window_timestamps:
                if previous is not None and timestamp <= previous:
                    continue
                if previous is None:
                    if timestamp != start:
                        results[start] = None
                        completed.append(start)
                        break
                elif (
                    timestamp - previous
                ).total_seconds() > _SESSION_GAP_SECONDS:
                    results[start] = (start, previous)
                    completed.append(start)
                    break
                previous = timestamp
            else:
                if previous is None:
                    results[start] = None
                    completed.append(start)
                elif (upper - previous).total_seconds() > _SESSION_GAP_SECONDS:
                    results[start] = (start, previous)
                    completed.append(start)
                else:
                    state["previous"] = previous
                    state["cursor"] = upper
        for start in completed:
            active.pop(start, None)

    for start in active:
        results[start] = None
    return {start: results.get(start) for start in starts}


def _previous_session_bounds(patient_id, before):
    """Find one prior stable session without materializing older aggregate rows."""
    end_query = _timestamp_query(patient_id)
    if before is not None:
        end_query = end_query.filter(DeviceRawData.collected_at < before)
    end_row = (
        end_query.distinct()
        .order_by(DeviceRawData.collected_at.desc())
        .first()
    )
    if end_row is None:
        return None

    end = end_row[0]
    newer = end
    cursor = end
    chunk = timedelta(minutes=_SESSION_BOUND_CHUNK_MINUTES)
    for _ in range(_SESSION_BOUND_MAX_CHUNKS):
        lower = cursor - chunk
        timestamps = [
            row[0]
            for row in (
                _timestamp_query(patient_id)
                .filter(DeviceRawData.collected_at >= lower)
                .filter(DeviceRawData.collected_at <= cursor)
                .distinct()
                .order_by(DeviceRawData.collected_at.desc())
                .all()
            )
        ]
        for timestamp in timestamps:
            if timestamp >= newer:
                continue
            if (newer - timestamp).total_seconds() > _SESSION_GAP_SECONDS:
                return newer, end
            newer = timestamp
        if (newer - lower).total_seconds() > _SESSION_GAP_SECONDS:
            return newer, end
        cursor = lower
    return None


def _parse_session_start(patient_id, session_id):
    match = _SESSION_ID_PATTERN.fullmatch(session_id)
    if match is None or match.group("patient_id") != str(patient_id):
        return None
    try:
        start = datetime.strptime(match.group("timestamp"), "%Y%m%dT%H%M%S%f")
    except (TypeError, ValueError, OverflowError):
        return None
    return start if _session_id(patient_id, start) == session_id else None


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


def _frame_page_selections(patient_id, bounds, page, page_size):
    """Select only timestamp groups whose logical frames overlap the page."""
    counts = (
        db.session.query(
            DeviceRawData.collected_at.label("timestamp"),
            func.sum(case((DeviceRawData.foot == "L", 1), else_=0)).label(
                "left_count"
            ),
            func.sum(case((DeviceRawData.foot == "R", 1), else_=0)).label(
                "right_count"
            ),
        )
        .filter(DeviceRawData.patient_id == patient_id)
        .filter(DeviceRawData.collected_at >= bounds[0])
        .filter(DeviceRawData.collected_at <= bounds[1])
        .group_by(DeviceRawData.collected_at)
        .subquery("frame_counts")
    )
    logical_count = case(
        (counts.c.left_count >= counts.c.right_count, counts.c.left_count),
        else_=counts.c.right_count,
    )
    total = db.session.query(
        func.coalesce(func.sum(logical_count), 0)
    ).select_from(counts).scalar()

    offset = (page - 1) * page_size
    page_end = offset + page_size
    current = counts.alias("current_counts")
    prior = counts.alias("prior_counts")
    current_logical_count = case(
        (current.c.left_count >= current.c.right_count, current.c.left_count),
        else_=current.c.right_count,
    )
    prior_logical_count = case(
        (prior.c.left_count >= prior.c.right_count, prior.c.left_count),
        else_=prior.c.right_count,
    )
    frame_offset = (
        select(func.coalesce(func.sum(prior_logical_count), 0))
        .select_from(prior)
        .where(prior.c.timestamp < current.c.timestamp)
        .correlate(current)
        .scalar_subquery()
    )
    page_groups = (
        db.session.query(
            current.c.timestamp,
            current.c.left_count,
            current.c.right_count,
            current_logical_count.label("frame_count"),
            frame_offset.label("frame_offset"),
        )
        .filter(frame_offset < page_end)
        .filter(frame_offset + current_logical_count > offset)
        .order_by(current.c.timestamp.asc())
        .limit(page_size)
        .all()
    )
    selections = [
        {
            "timestamp": timestamp,
            "start": max(offset - frame_offset_value, 0),
            "end": min(page_end - frame_offset_value, frame_count),
            "left_count": left_count,
            "right_count": right_count,
        }
        for timestamp, left_count, right_count, frame_count, frame_offset_value
        in page_groups
    ]
    return int(total), selections


def _frame_page_rows(patient_id, selections):
    """Load only the raw rows required for selected logical frame ordinals."""
    rows_by_timestamp = {}
    whole_timestamps = [
        selection["timestamp"]
        for selection in selections
        if selection["start"] == 0
        and selection["end"]
        == max(selection["left_count"], selection["right_count"])
    ]
    if whole_timestamps:
        for row in _fetch_rows(
            patient_id,
            timestamps=whole_timestamps,
            include_sensors=True,
        ):
            rows_by_timestamp.setdefault(row["collected_at"], {"L": [], "R": []})[
                row["foot"]
            ].append(row)

    for selection in selections:
        if selection["timestamp"] in whole_timestamps:
            continue
        rows_by_timestamp[selection["timestamp"]] = {"L": [], "R": []}
        for foot, count_key in (("L", "left_count"), ("R", "right_count")):
            count = selection[count_key]
            start = min(selection["start"], count)
            end = min(selection["end"], count)
            if start < end:
                rows_by_timestamp[selection["timestamp"]][foot] = _fetch_rows(
                    patient_id,
                    timestamps=[selection["timestamp"]],
                    foot=foot,
                    offset=start,
                    limit=end - start,
                    include_sensors=True,
                )
    return rows_by_timestamp


def _page_frames(selections, rows_by_timestamp):
    frames = []
    for selection in selections:
        feet = rows_by_timestamp[selection["timestamp"]]
        for ordinal in range(selection["start"], selection["end"]):
            frames.append(
                {
                    "collected_at": selection["timestamp"],
                    "L": (
                        feet["L"][ordinal - selection["start"]]
                        if ordinal < selection["left_count"]
                        else None
                    ),
                    "R": (
                        feet["R"][ordinal - selection["start"]]
                        if ordinal < selection["right_count"]
                        else None
                    ),
                }
            )
    return frames


def _load_bounded_sessions(patient_id, target_ranges, *, history_before):
    """Load target ranges and only enough prior candidates for five usable sessions."""
    target_ranges = list(dict.fromkeys(target_ranges))
    target_sessions = {}
    eligible_history_newest = []
    cursor = history_before
    first_batch = True

    while first_batch or len(eligible_history_newest) < _HISTORY_BATCH_SIZE:
        candidate_ranges = []
        for _ in range(_HISTORY_BATCH_SIZE):
            bounds = _previous_session_bounds(patient_id, cursor)
            if bounds is None:
                break
            candidate_ranges.append(bounds)
            cursor = bounds[0]

        ranges = [
            *candidate_ranges,
            *(target_ranges if first_batch else []),
        ]
        first_batch = False
        if not ranges:
            break

        sessions = segment_sessions(
            _fetch_rows(patient_id, ranges=ranges, include_sensors=False),
            gap_seconds=_SESSION_GAP_SECONDS,
        )
        sessions_by_start = {session["start"]: session for session in sessions}
        for session in sessions:
            if any(
                lower <= session["start"] <= upper
                for lower, upper in target_ranges
            ):
                target_sessions[session["start"]] = session

        for lower, _upper in candidate_ranges:
            session = sessions_by_start.get(lower)
            if session is None:
                continue
            summary = _session_summary(session, patient_id, [])
            if summary["data_quality"]["status"] in {"complete", "usable"}:
                eligible_history_newest.append(summary)
                if len(eligible_history_newest) == _HISTORY_BATCH_SIZE:
                    break

        if (
            not candidate_ranges
            or len(eligible_history_newest) == _HISTORY_BATCH_SIZE
        ):
            break

    return list(reversed(eligible_history_newest)), target_sessions


def _public_summary(summary):
    return {key: value for key, value in summary.items() if key != "patient_id"}


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


def _invalid_session_id_response():
    return jsonify(Response.error(422, "invalid session_id format")), 422


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
    history, sessions_by_start = _load_bounded_sessions(
        patient_id,
        [(starts[0], final_bounds[1])],
        history_before=starts[0],
    )
    summaries = []
    running_history = list(history)
    for session_start in starts:
        session = sessions_by_start.get(session_start)
        if session is None:
            continue
        summary = _session_summary(session, patient_id, running_history)
        running_history.append(summary)
        summaries.append(_public_summary(summary))
    summaries.reverse()
    return jsonify(Response.success(data={"total": len(summaries), "sessions": summaries}))


@gait_bp.route("/patients/<int:patient_id>/gait/sessions/<string:session_id>", methods=["GET"])
@token_required()
def get_gait_session(patient_id, session_id):
    _, error = _owned_patient_or_resp(patient_id)
    if error:
        return error

    start = _parse_session_start(patient_id, session_id)
    if start is None:
        return _invalid_session_id_response()
    bounds = _session_bounds_for_start(patient_id, start)
    if bounds is None:
        return _session_not_found_response()

    history, sessions_by_start = _load_bounded_sessions(
        patient_id,
        [bounds],
        history_before=bounds[0],
    )
    aggregate_session_record = sessions_by_start.get(bounds[0])
    session = _session_for_bounds(patient_id, bounds, include_sensors=True)
    if aggregate_session_record is None or session is None:
        return _session_not_found_response()

    summary = _session_summary(aggregate_session_record, patient_id, history)
    data = _public_summary(summary)
    data["pressure_summary"] = summarize_pressure_rows(
        _fetch_pressure_rows_for_bounds(patient_id, bounds)
    )
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
    if session_start is None:
        return _invalid_session_id_response()
    bounds = _session_bounds_for_start(patient_id, session_start)
    if bounds is None:
        return _session_not_found_response()

    page = _page_arg("page", 1)
    page_size = _page_arg("page_size", _PAGE_SIZE_DEFAULT, _PAGE_SIZE_MAX)
    total, selections = _frame_page_selections(patient_id, bounds, page, page_size)
    frames = _page_frames(selections, _frame_page_rows(patient_id, selections))
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
    starts = [
        _parse_session_start(patient_id, session_id)
        for session_id in session_ids
    ]
    if any(start is None for start in starts):
        return _invalid_session_id_response()

    bounds_by_start = _session_bounds_for_starts(patient_id, starts)
    if any(bounds_by_start.get(start) is None for start in starts):
        return _session_not_found_response()
    target_ranges = [bounds_by_start[start] for start in starts]
    history, sessions_by_start = _load_bounded_sessions(
        patient_id,
        target_ranges,
        history_before=None,
    )
    summaries_by_id = {
        summary["session_id"]: summary
        for summary in history
    }
    for start in starts:
        session = sessions_by_start.get(start)
        if session is None:
            continue
        summary = _session_summary(session, patient_id, [])
        summaries_by_id[summary["session_id"]] = summary
    summaries = sorted(
        summaries_by_id.values(),
        key=lambda summary: summary["start"],
    )
    try:
        data = compare_session_summaries(summaries, session_ids)
    except ValueError as error:
        return jsonify(Response.error(422, str(error))), 422
    return jsonify(Response.success(data=data))
