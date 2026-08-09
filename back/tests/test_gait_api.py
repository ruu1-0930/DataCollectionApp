"""Integration tests for the stable gait data workbench API."""

import json
import math
import re
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from api import gait as gait_api
from config import db
from models.models import DeviceRawData


_BASE_TIME = datetime(2026, 7, 12, 9, 42, 3, 123000)


def _clinical_frame(**overrides):
    data = {
        **{f"lp{i}": 1000 for i in range(1, 10)},
        "ax": 1,
        "ay": 2,
        "az": 3,
        "gx": 4,
        "gy": 5,
        "gz": 6,
        "left_step_size": 0.6,
        "left_speed": 1.1,
        "left_single_sp_time": 0.4,
        "left_double_sp_time": 0.2,
        **{f"rp{i}": 1100 for i in range(1, 10)},
        "right_ax": 11,
        "right_ay": 12,
        "right_az": 13,
        "right_gx": 14,
        "right_gy": 15,
        "right_gz": 16,
        "right_step_size": 0.6,
        "right_speed": 1.1,
        "right_single_sp_time": 0.4,
        "right_double_sp_time": 0.2,
    }
    data.update(overrides)
    return data


def _setup(client, frame_count=1):
    token = client.post(
        "/clinician/enable",
        json={
            "hospital": "H",
            "dept": "D",
            "name": "Dr",
            "phone": "13800000000",
            "passcode": "1234",
        },
    ).get_json()["data"]["token"]
    auth = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/patients",
        headers=auth,
        json={"name": "A", "phone": "13700000000", "age": 72},
    ).get_json()["data"]["id"]
    client.post("/devices", headers=auth, json={"device_code": "INSOLE-001"})

    for _ in range(frame_count):
        frame = _clinical_frame(patient_id=patient_id)
        response = client.post("/devices/INSOLE-001/raw_data", headers=auth, json=frame)
        assert response.status_code == 200
    return auth, patient_id


def _session_id(patient_id, start):
    return f"P{patient_id}-{start:%Y%m%dT%H%M%S}{start.microsecond // 1000:03d}"


def _set_frame_times(patient_id, frame_times, walking_speeds=None):
    rows = (
        DeviceRawData.query.filter_by(patient_id=patient_id)
        .order_by(DeviceRawData.id.asc())
        .all()
    )
    assert len(rows) == len(frame_times) * 2

    for index, start in enumerate(frame_times):
        pair = rows[index * 2:(index + 1) * 2]
        assert {row.foot for row in pair} == {"L", "R"}
        for row in pair:
            row.collected_at = start
            if walking_speeds is not None:
                row.walking_speed = walking_speeds[index]
    db.session.commit()


def _setup_sessions(client, starts, walking_speeds=None):
    auth, patient_id = _setup(client, frame_count=len(starts))
    _set_frame_times(patient_id, starts, walking_speeds)
    return auth, patient_id, [_session_id(patient_id, start) for start in starts]


def _setup_session(client, frames=1):
    starts = [_BASE_TIME + timedelta(seconds=index) for index in range(frames)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    return auth, patient_id, session_ids[0]


def _request_session_endpoint(
    client,
    endpoint,
    *,
    auth,
    patient_id,
    session_id,
    comparison_baseline_id,
):
    if endpoint == "compare":
        return client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": [comparison_baseline_id, session_id]},
        )
    suffix = "/frames" if endpoint == "frames" else ""
    return client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}{suffix}",
        headers=auth,
    )


def _noncanonical_session_id(kind, patient_id, start):
    timestamp = f"{start:%Y%m%dT%H%M%S}{start.microsecond // 1000:03d}"
    if kind == "leading_zero":
        return f"P{patient_id:05d}-{timestamp}"
    if kind == "too_long":
        return f"P{'9' * 5000}-{timestamp}"
    return f"P{patient_id}-{timestamp}-extra"


def _create_other_clinician_auth(client):
    token = client.post(
        "/clinician/enable",
        json={
            "hospital": "H",
            "dept": "D",
            "name": "Dr2",
            "phone": "13900000000",
            "passcode": "1234",
        },
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


def _capture_raw_selects(action):
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select") and "device_raw_data" in normalized:
            statements.append(normalized)

    event.listen(db.engine, "before_cursor_execute", record_sql)
    try:
        response = action()
    finally:
        event.remove(db.engine, "before_cursor_execute", record_sql)
    return response, statements


def _capture_loaded_aggregate_timestamps(monkeypatch, action):
    loaded_timestamps = []
    original_fetch_rows = gait_api._fetch_rows

    def tracked_fetch_rows(*args, **kwargs):
        rows = original_fetch_rows(*args, **kwargs)
        loaded_timestamps.extend(row["collected_at"] for row in rows)
        return rows

    monkeypatch.setattr(gait_api, "_fetch_rows", tracked_fetch_rows)
    return action(), loaded_timestamps


def _capture_loaded_aggregate_batches(monkeypatch, action):
    loaded_batches = []
    original_fetch_rows = gait_api._fetch_rows

    def tracked_fetch_rows(*args, **kwargs):
        rows = original_fetch_rows(*args, **kwargs)
        if not kwargs.get("include_sensors", False):
            loaded_batches.append([row["collected_at"] for row in rows])
        return rows

    monkeypatch.setattr(gait_api, "_fetch_rows", tracked_fetch_rows)
    return action(), loaded_batches


def _capture_loaded_sensor_timestamps(monkeypatch, action):
    loaded_timestamps = []
    original_fetch_rows = gait_api._fetch_rows

    def tracked_fetch_rows(*args, **kwargs):
        rows = original_fetch_rows(*args, **kwargs)
        if kwargs.get("include_sensors", False):
            loaded_timestamps.extend(row["collected_at"] for row in rows)
        return rows

    monkeypatch.setattr(gait_api, "_fetch_rows", tracked_fetch_rows)
    return action(), loaded_timestamps


def _setup_bounded_history_scenario(client):
    old_starts = [
        _BASE_TIME - timedelta(days=10) + timedelta(minutes=index)
        for index in range(20)
    ]
    recent_starts = [
        _BASE_TIME + timedelta(minutes=index)
        for index in range(5)
    ]
    target_starts = [
        _BASE_TIME + timedelta(minutes=5),
        _BASE_TIME + timedelta(minutes=6),
    ]
    speeds = [
        *([99.0] * len(old_starts)),
        0.6,
        0.7,
        0.8,
        0.9,
        1.0,
        1.2,
        1.4,
    ]
    auth, patient_id, session_ids = _setup_sessions(
        client,
        [*old_starts, *recent_starts, *target_starts],
        walking_speeds=speeds,
    )
    return {
        "auth": auth,
        "patient_id": patient_id,
        "old_starts": old_starts,
        "recent_starts": recent_starts,
        "target_starts": target_starts,
        "target_ids": session_ids[-2:],
    }


def _setup_history_beyond_limited_sessions(client, *, trailing_target):
    old_starts = [
        _BASE_TIME - timedelta(days=10) + timedelta(minutes=index)
        for index in range(5)
    ]
    qualified_starts = [
        _BASE_TIME + timedelta(minutes=index)
        for index in range(5)
    ]
    limited_starts = [
        _BASE_TIME + timedelta(minutes=5 + index)
        for index in range(30)
    ]
    target_starts = (
        [_BASE_TIME + timedelta(minutes=35)]
        if trailing_target
        else []
    )
    starts = [*old_starts, *qualified_starts, *limited_starts, *target_starts]
    speeds = [
        *([99.0] * len(old_starts)),
        0.0,
        0.8,
        1.0,
        1.2,
        1.4,
        *([9.0] * (len(limited_starts) + len(target_starts))),
    ]
    auth, patient_id, session_ids = _setup_sessions(
        client,
        starts,
        walking_speeds=speeds,
    )
    unpaired_starts = [*limited_starts, *target_starts]
    (
        DeviceRawData.query.filter(
            DeviceRawData.patient_id == patient_id,
            DeviceRawData.foot == "R",
            DeviceRawData.collected_at.in_(unpaired_starts),
        )
        .delete(synchronize_session=False)
    )
    db.session.commit()
    return {
        "auth": auth,
        "patient_id": patient_id,
        "old_starts": old_starts,
        "qualified_starts": qualified_starts,
        "limited_starts": limited_starts,
        "target_ids": session_ids[-len(target_starts):] if target_starts else [],
        "qualified_ids": session_ids[len(old_starts):len(old_starts) + 5],
    }


def test_session_filters_include_canonical_start_boundaries(client):
    starts = [
        _BASE_TIME,
        _BASE_TIME + timedelta(minutes=1),
        _BASE_TIME + timedelta(minutes=2),
    ]
    auth, patient_id, session_ids = _setup_sessions(client, starts)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={"start": starts[1].isoformat(), "end": starts[2].isoformat()},
    )
    assert response.status_code == 200
    sessions = response.get_json()["data"]["sessions"]

    assert [session["session_id"] for session in sessions] == [session_ids[2], session_ids[1]]


def test_date_only_end_includes_entire_day_and_excludes_next_midnight(client):
    morning = datetime(2026, 7, 12, 9, 0)
    evening = datetime(2026, 7, 12, 23, 59)
    next_midnight = datetime(2026, 7, 13, 0, 0)
    auth, patient_id, session_ids = _setup_sessions(
        client,
        [morning, evening, next_midnight],
    )

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={"start": "2026-07-12", "end": "2026-07-12"},
    )

    assert response.status_code == 200
    assert [
        session["session_id"] for session in response.get_json()["data"]["sessions"]
    ] == [session_ids[1], session_ids[0]]


def test_session_filter_keeps_cross_boundary_session_canonical_and_accessible(client):
    session_start = _BASE_TIME
    session_continuation = session_start + timedelta(seconds=20)
    later_session_start = session_start + timedelta(minutes=2)
    auth, patient_id, _ = _setup_sessions(
        client,
        [session_start, session_continuation, later_session_start],
    )
    canonical_id = _session_id(patient_id, session_start)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={"start": session_start.isoformat(), "end": session_start.isoformat()},
    )
    assert response.status_code == 200
    sessions = response.get_json()["data"]["sessions"]

    assert [session["session_id"] for session in sessions] == [canonical_id]
    assert sessions[0]["frame_count"] == 2
    assert client.get(
        f"/patients/{patient_id}/gait/sessions/{canonical_id}",
        headers=auth,
    ).status_code == 200
    frames = client.get(
        f"/patients/{patient_id}/gait/sessions/{canonical_id}/frames",
        headers=auth,
    ).get_json()["data"]
    assert frames["total"] == 2


def test_session_filter_does_not_create_suffix_session_when_start_is_inside_session(client):
    session_start = _BASE_TIME
    session_continuation = session_start + timedelta(seconds=20)
    later_session_start = session_start + timedelta(minutes=2)
    auth, patient_id, _ = _setup_sessions(
        client,
        [session_start, session_continuation, later_session_start],
    )
    later_session_id = _session_id(patient_id, later_session_start)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={
            "start": (session_start + timedelta(seconds=10)).isoformat(),
            "end": later_session_start.isoformat(),
        },
    )
    assert response.status_code == 200

    assert [session["session_id"] for session in response.get_json()["data"]["sessions"]] == [
        later_session_id
    ]


@pytest.mark.parametrize(
    "query_string",
    [
        {"start": "not-an-iso-datetime"},
        {"start": "2026-07-12T09:42:03Z"},
        {"end": "2026-07-12T17:42:03+08:00"},
    ],
)
def test_session_filters_reject_malformed_or_timezone_aware_datetimes(client, query_string):
    auth, patient_id, _ = _setup_session(client)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string=query_string,
    )
    assert response.status_code == 422


def test_session_filters_reject_reversed_datetime_range(client):
    auth, patient_id, _ = _setup_session(client)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={
            "start": (_BASE_TIME + timedelta(minutes=1)).isoformat(),
            "end": _BASE_TIME.isoformat(),
        },
    )
    assert response.status_code == 422


def test_session_filters_reject_adjacent_reversed_date_only_range(client):
    auth, patient_id, _ = _setup_session(client)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={"start": "2026-07-13", "end": "2026-07-12"},
    )

    assert response.status_code == 422


def test_sessions_return_stable_ids_newest_first(client):
    older_start = _BASE_TIME
    newer_start = _BASE_TIME + timedelta(minutes=1)
    auth, patient_id, session_ids = _setup_sessions(client, [older_start, newer_start])

    response = client.get(f"/patients/{patient_id}/gait/sessions", headers=auth)
    assert response.status_code == 200
    sessions = response.get_json()["data"]["sessions"]

    assert [session["session_id"] for session in sessions] == list(reversed(session_ids))
    assert sessions[0]["start"] > sessions[1]["start"]
    assert re.fullmatch(rf"P{patient_id}-\d{{8}}T\d{{9}}", sessions[0]["session_id"])
    assert "session_index" not in sessions[0]


def test_exact_thirty_second_gap_stays_joined_and_one_microsecond_splits_across_chunk(
    client,
):
    first_start = _BASE_TIME
    first_session_times = [
        first_start + timedelta(seconds=30 * index)
        for index in range(10)
    ]
    first_session_times.append(
        first_start + timedelta(seconds=299, microseconds=876999)
    )
    second_start = first_session_times[-1] + timedelta(
        seconds=30,
        microseconds=1,
    )
    auth, patient_id, _ = _setup_sessions(
        client,
        [*first_session_times, second_start],
    )
    first_id = _session_id(patient_id, first_start)
    second_id = _session_id(patient_id, second_start)

    list_response = client.get(
        f"/patients/{patient_id}/gait/sessions",
        headers=auth,
        query_string={
            "start": first_start.isoformat(),
            "end": second_start.isoformat(),
        },
    )
    detail_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{first_id}",
        headers=auth,
    )
    compare_response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": [first_id, second_id]},
    )

    assert list_response.status_code == 200
    sessions = list_response.get_json()["data"]["sessions"]
    assert [session["session_id"] for session in sessions] == [second_id, first_id]
    first_summary = next(
        session for session in sessions
        if session["session_id"] == first_id
    )
    assert first_summary["frame_count"] == 11
    assert first_summary["end"] == first_session_times[-1].isoformat()
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["frame_count"] == 11
    assert compare_response.status_code == 200
    assert compare_response.get_json()["data"]["session_ids"] == [
        first_id,
        second_id,
    ]


def test_session_list_bulk_loads_aggregate_rows_once_for_narrow_and_wide_ranges(client):
    starts = [_BASE_TIME + timedelta(minutes=index) for index in range(7)]
    auth, patient_id, _ = _setup_sessions(client, starts)

    narrow_response, narrow_statements = _capture_raw_selects(
        lambda: client.get(
            f"/patients/{patient_id}/gait/sessions",
            headers=auth,
            query_string={
                "start": starts[0].isoformat(),
                "end": starts[1].isoformat(),
            },
        )
    )
    wide_response, wide_statements = _capture_raw_selects(
        lambda: client.get(
            f"/patients/{patient_id}/gait/sessions",
            headers=auth,
            query_string={
                "start": starts[0].isoformat(),
                "end": starts[-1].isoformat(),
            },
        )
    )

    assert narrow_response.status_code == 200
    assert wide_response.status_code == 200
    assert len(narrow_statements) == len(wide_statements)
    assert sum("device_raw_data.walking_speed" in sql for sql in narrow_statements) == 1
    assert sum("device_raw_data.walking_speed" in sql for sql in wide_statements) == 1


def test_narrow_session_list_does_not_materialize_older_aggregate_history(
    client,
    monkeypatch,
):
    scenario = _setup_bounded_history_scenario(client)
    target_start = scenario["target_starts"][0]

    response, loaded_timestamps = _capture_loaded_aggregate_timestamps(
        monkeypatch,
        lambda: client.get(
            f"/patients/{scenario['patient_id']}/gait/sessions",
            headers=scenario["auth"],
            query_string={
                "start": target_start.isoformat(),
                "end": target_start.isoformat(),
            },
        ),
    )

    assert response.status_code == 200
    sessions = response.get_json()["data"]["sessions"]
    assert [session["session_id"] for session in sessions] == [scenario["target_ids"][0]]
    speed_flag = next(
        flag
        for flag in sessions[0]["flags"]
        if flag["metric_key"] == "walking_speed_mps"
    )
    assert speed_flag["history"]["median"] == pytest.approx(0.8)
    assert loaded_timestamps
    assert min(loaded_timestamps) >= scenario["recent_starts"][0]
    assert not set(loaded_timestamps).intersection(scenario["old_starts"])


def test_session_detail_uses_step_length_without_inline_frames(client):
    auth, patient_id, session_id = _setup_session(client)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}",
        headers=auth,
    )
    assert response.status_code == 200
    data = response.get_json()["data"]

    assert data["session_id"] == session_id
    assert data["metrics"]["step_length_m"]["value"] == pytest.approx(0.6)
    assert "frames" not in data
    assert "stride_length" not in json.dumps(data)


def test_session_detail_includes_pressure_summary_contract(client):
    auth, patient_id, session_id = _setup_session(client)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}",
        headers=auth,
    )

    assert response.status_code == 200
    summary = response.get_json()["data"]["pressure_summary"]
    assert summary["method"] == "nonzero_mean_v1"
    assert summary["unit"] == "ADC"
    assert set(summary["left"]["sensors"]) == {f"p{i}" for i in range(1, 10)}
    assert summary["attention"]["quality"] in {
        "usable",
        "partial",
        "insufficient",
    }


def test_full_session_pressure_summary_uses_all_501_frames_before_chart_sampling(client):
    auth, patient_id, session_id = _setup_session(client, frames=501)
    left_rows = (
        DeviceRawData.query.filter_by(patient_id=patient_id, foot="L")
        .order_by(DeviceRawData.collected_at.asc())
        .all()
    )
    assert len(left_rows) == 501
    for index, row in enumerate(left_rows, start=1):
        row.p1 = float(index)
    db.session.commit()

    detail = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}",
        headers=auth,
    ).get_json()["data"]

    assert detail["chart_series"]["total_points"] == 501
    assert len(detail["chart_series"]["items"]) == 500
    assert (
        detail["pressure_summary"]["left"]["sensors"]["p1"]["valid_samples"]
        == 501
    )
    assert detail["pressure_summary"]["left"]["sensors"]["p1"][
        "mean_adc"
    ] == pytest.approx(251.0)


def test_session_detail_only_materializes_target_and_recent_five_aggregate_rows(
    client,
    monkeypatch,
):
    scenario = _setup_bounded_history_scenario(client)

    response, loaded_timestamps = _capture_loaded_aggregate_timestamps(
        monkeypatch,
        lambda: client.get(
            (
                f"/patients/{scenario['patient_id']}/gait/sessions/"
                f"{scenario['target_ids'][0]}"
            ),
            headers=scenario["auth"],
        ),
    )

    assert response.status_code == 200
    speed_flag = next(
        flag
        for flag in response.get_json()["data"]["flags"]
        if flag["metric_key"] == "walking_speed_mps"
    )
    assert speed_flag["history"]["median"] == pytest.approx(0.8)
    assert loaded_timestamps
    assert min(loaded_timestamps) >= scenario["recent_starts"][0]
    assert not set(loaded_timestamps).intersection(scenario["old_starts"])


def test_session_detail_scans_past_thirty_limited_sessions_for_five_usable_flags(
    client,
    monkeypatch,
):
    scenario = _setup_history_beyond_limited_sessions(
        client,
        trailing_target=True,
    )

    response, loaded_batches = _capture_loaded_aggregate_batches(
        monkeypatch,
        lambda: client.get(
            (
                f"/patients/{scenario['patient_id']}/gait/sessions/"
                f"{scenario['target_ids'][0]}"
            ),
            headers=scenario["auth"],
        ),
    )

    assert response.status_code == 200
    speed_flag = next(
        flag
        for flag in response.get_json()["data"]["flags"]
        if flag["metric_key"] == "walking_speed_mps"
    )
    assert speed_flag["history"]["median"] == pytest.approx(1.0)
    assert len(loaded_batches) == 7
    assert all(len(set(batch)) <= 6 for batch in loaded_batches)
    loaded_timestamps = {
        timestamp
        for batch in loaded_batches
        for timestamp in batch
    }
    assert 0.0 in [
        row.walking_speed
        for row in DeviceRawData.query.filter(
            DeviceRawData.patient_id == scenario["patient_id"],
            DeviceRawData.collected_at.in_(scenario["qualified_starts"]),
        ).all()
    ]
    assert not loaded_timestamps.intersection(scenario["old_starts"])
    assert min(loaded_timestamps) == scenario["qualified_starts"][0]


def test_frames_are_paginated_and_raw_units_are_explicit(client):
    auth, patient_id, session_id = _setup_session(client, frames=12)

    response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}/frames?page=2&page_size=5",
        headers=auth,
    )
    assert response.status_code == 200
    data = response.get_json()["data"]

    assert data["total"] == 12
    assert data["page"] == 2
    assert data["page_size"] == 5
    assert len(data["items"]) == 5
    assert data["items"][0]["left"]["pressure_unit"] == "ADC"
    assert data["items"][0]["left"]["imu_unit"] == "raw_unscaled"
    assert data["items"][0]["right"]["pressure_unit"] == "ADC"
    assert data["items"][0]["right"]["imu_unit"] == "raw_unscaled"
    assert "pressure_summary" not in data


def test_frames_use_default_and_capped_page_sizes(client):
    auth, patient_id, session_id = _setup_session(client, frames=12)

    default_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}/frames",
        headers=auth,
    )
    assert default_response.status_code == 200
    assert default_response.get_json()["data"]["page_size"] == 100

    capped_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}/frames?page_size=999",
        headers=auth,
    )
    assert capped_response.status_code == 200
    assert capped_response.get_json()["data"]["page_size"] == 500


def test_frames_page_does_not_load_entire_session_as_raw_models(client):
    auth, patient_id, session_id = _setup_session(client, frames=20)
    db.session.expunge_all()
    loaded_raw_ids = []

    def record_load(raw, _context):
        loaded_raw_ids.append(raw.id)

    event.listen(DeviceRawData, "load", record_load)
    try:
        response = client.get(
            f"/patients/{patient_id}/gait/sessions/{session_id}/frames",
            headers=auth,
            query_string={"page": 2, "page_size": 3},
        )
    finally:
        event.remove(DeviceRawData, "load", record_load)

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["total"] == 20
    assert len(data["items"]) == 3
    assert len(loaded_raw_ids) <= 6


def test_session_list_queries_only_aggregation_columns(client):
    auth, patient_id, _ = _setup_session(client, frames=3)
    statements = []

    def record_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "device_raw_data" in statement:
            statements.append(statement.lower())

    event.listen(db.engine, "before_cursor_execute", record_sql)
    try:
        response = client.get(f"/patients/{patient_id}/gait/sessions", headers=auth)
    finally:
        event.remove(db.engine, "before_cursor_execute", record_sql)

    assert response.status_code == 200
    assert statements
    assert all(
        "pressure_summary" not in session
        for session in response.get_json()["data"]["sessions"]
    )
    assert all("device_raw_data.p1" not in statement for statement in statements)
    assert all("device_raw_data.ax" not in statement for statement in statements)


def test_target_session_detail_materializes_only_target_session_sensor_rows(
    client,
    monkeypatch,
):
    starts = [
        *[_BASE_TIME + timedelta(seconds=index) for index in range(4)],
        *[_BASE_TIME + timedelta(minutes=2, seconds=index) for index in range(4)],
    ]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    response, loaded_timestamps = _capture_loaded_sensor_timestamps(
        monkeypatch,
        lambda: client.get(
            f"/patients/{patient_id}/gait/sessions/{session_ids[0]}",
            headers=auth,
        ),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["frame_count"] == 4
    assert set(loaded_timestamps) == set(starts[:4])
    assert not set(loaded_timestamps).intersection(starts[4:])


def test_non_finite_raw_values_return_null_without_json_failure(client):
    auth, patient_id, session_id = _setup_session(client)
    rows = DeviceRawData.query.filter_by(patient_id=patient_id).all()
    for raw in rows:
        raw.walking_speed = math.inf
        raw.p1 = math.inf
        raw.ax = -math.inf
    db.session.commit()

    detail_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}",
        headers=auth,
    )
    frames_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_id}/frames",
        headers=auth,
    )

    assert detail_response.status_code == 200
    assert frames_response.status_code == 200
    assert "Infinity" not in detail_response.get_data(as_text=True)
    assert "Infinity" not in frames_response.get_data(as_text=True)
    detail = detail_response.get_json()["data"]
    frame = frames_response.get_json()["data"]["items"][0]
    assert detail["metrics"]["walking_speed_mps"]["value"] is None
    assert detail["data_quality"]["missing_required_values"] == 2
    assert next(
        flag
        for flag in detail["flags"]
        if flag["metric_key"] == "walking_speed_mps"
    )["status"] == "unknown"
    assert frame["left"]["pressure"]["p1"] is None
    assert frame["left"]["imu"]["ax"] is None
    assert frame["left"]["walking_speed_mps"] is None


def test_finite_extreme_values_do_not_overflow_gait_json(client):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(
        client,
        starts,
        walking_speeds=[-1e308, 1e308],
    )

    detail_response = client.get(
        f"/patients/{patient_id}/gait/sessions/{session_ids[1]}",
        headers=auth,
    )
    compare_response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": session_ids},
    )

    assert detail_response.status_code == 200
    assert compare_response.status_code == 200
    assert "Infinity" not in detail_response.get_data(as_text=True)
    assert "NaN" not in detail_response.get_data(as_text=True)
    assert "Infinity" not in compare_response.get_data(as_text=True)
    assert "NaN" not in compare_response.get_data(as_text=True)
    comparison_row = compare_response.get_json()["data"]["metrics"]["walking_speed_mps"][1]
    assert comparison_row["delta_abs"] is None
    assert comparison_row["delta_pct"] is None
    assert comparison_row["reason"] == "value_unavailable"
    speed_flag = next(
        flag
        for flag in detail_response.get_json()["data"]["flags"]
        if flag["metric_key"] == "walking_speed_mps"
    )
    assert speed_flag["status"] == "unknown"


@pytest.mark.parametrize("endpoint", ["detail", "frames", "compare"])
@pytest.mark.parametrize(
    "invalid_kind",
    ["leading_zero", "too_long", "other_noncanonical"],
)
def test_noncanonical_session_ids_are_422_before_any_raw_query(
    client,
    endpoint,
    invalid_kind,
):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    invalid_id = _noncanonical_session_id(
        invalid_kind,
        patient_id,
        starts[1],
    )

    response, statements = _capture_raw_selects(
        lambda: _request_session_endpoint(
            client,
            endpoint,
            auth=auth,
            patient_id=patient_id,
            session_id=invalid_id,
            comparison_baseline_id=session_ids[0],
        )
    )

    assert response.status_code == 422
    assert statements == []


@pytest.mark.parametrize("endpoint", ["detail", "frames", "compare"])
def test_canonical_missing_session_ids_are_404(client, endpoint):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    missing_id = _session_id(patient_id, _BASE_TIME + timedelta(days=1))

    response = _request_session_endpoint(
        client,
        endpoint,
        auth=auth,
        patient_id=patient_id,
        session_id=missing_id,
        comparison_baseline_id=session_ids[0],
    )

    assert response.status_code == 404


@pytest.mark.parametrize("endpoint", ["detail", "frames", "compare"])
def test_canonical_existing_session_ids_are_200(client, endpoint):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)

    response = _request_session_endpoint(
        client,
        endpoint,
        auth=auth,
        patient_id=patient_id,
        session_id=session_ids[1],
        comparison_baseline_id=session_ids[0],
    )

    assert response.status_code == 200


@pytest.mark.parametrize("count", [1, 6])
def test_compare_rejects_session_counts_outside_two_to_five(client, count):
    auth, patient_id, session_ids = _setup_sessions(
        client,
        [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)],
    )

    response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": (session_ids * 3)[:count]},
    )
    assert response.status_code == 422


def test_compare_rejects_duplicate_session_ids(client):
    auth, patient_id, session_ids = _setup_sessions(
        client,
        [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)],
    )

    response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": [session_ids[0], session_ids[0]]},
    )
    assert response.status_code == 422


def test_invalid_compare_payloads_execute_zero_raw_queries(client):
    starts = [_BASE_TIME + timedelta(minutes=index) for index in range(6)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    invalid_session_ids = [
        [],
        [session_ids[0]],
        session_ids,
        [session_ids[0], session_ids[0]],
        [session_ids[0], "not-a-session-id"],
    ]

    for selected in invalid_session_ids:
        response, statements = _capture_raw_selects(
            lambda selected=selected: client.post(
                f"/patients/{patient_id}/gait/compare",
                headers=auth,
                json={"session_ids": selected},
            )
        )
        assert response.status_code == 422
        assert statements == []


@pytest.mark.parametrize(
    "invalid_id_factory",
    [
        lambda patient_id, start: (
            f"P{patient_id:05d}-{start:%Y%m%dT%H%M%S}"
            f"{start.microsecond // 1000:03d}"
        ),
        lambda _patient_id, start: (
            f"P{'9' * 5000}-{start:%Y%m%dT%H%M%S}"
            f"{start.microsecond // 1000:03d}"
        ),
    ],
)
def test_noncanonical_compare_session_ids_execute_zero_raw_queries(
    client,
    invalid_id_factory,
):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)
    invalid_id = invalid_id_factory(patient_id, starts[1])

    response, statements = _capture_raw_selects(
        lambda: client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": [session_ids[0], invalid_id]},
        )
    )

    assert response.status_code == 422
    assert statements == []


def test_compare_bulk_loads_once_with_constant_query_count_for_two_or_five_sessions(client):
    starts = [_BASE_TIME + timedelta(minutes=index) for index in range(7)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)

    two_response, two_statements = _capture_raw_selects(
        lambda: client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": session_ids[:2]},
        )
    )
    five_response, five_statements = _capture_raw_selects(
        lambda: client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": session_ids[:5]},
        )
    )

    assert two_response.status_code == 200
    assert five_response.status_code == 200
    assert len(two_statements) == len(five_statements)
    assert sum("device_raw_data.walking_speed" in sql for sql in two_statements) == 1
    assert sum("device_raw_data.walking_speed" in sql for sql in five_statements) == 1


def test_compare_omits_pressure_summary_and_queries_only_aggregation_columns(client):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)

    response, statements = _capture_raw_selects(
        lambda: client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": session_ids},
        )
    )

    assert response.status_code == 200
    assert "pressure_summary" not in json.dumps(response.get_json()["data"])
    assert statements
    assert all("device_raw_data.p1" not in statement for statement in statements)
    assert all("device_raw_data.ax" not in statement for statement in statements)


def test_compare_materializes_only_selected_and_fixed_recent_five_sessions(
    client,
    monkeypatch,
):
    scenario = _setup_bounded_history_scenario(client)

    response, loaded_timestamps = _capture_loaded_aggregate_timestamps(
        monkeypatch,
        lambda: client.post(
            f"/patients/{scenario['patient_id']}/gait/compare",
            headers=scenario["auth"],
            json={"session_ids": scenario["target_ids"]},
        ),
    )

    assert response.status_code == 200
    history_baselines = response.get_json()["data"]["history_baselines"]
    assert history_baselines["walking_speed_mps"] == {
        "median": pytest.approx(1.0),
        "reason": None,
    }
    assert history_baselines["cadence_spm"] == {
        "median": pytest.approx(100.0),
        "reason": None,
    }
    assert len(history_baselines) == 8
    assert loaded_timestamps
    assert min(loaded_timestamps) >= scenario["recent_starts"][2]
    assert not set(loaded_timestamps).intersection(scenario["old_starts"])


def test_compare_scans_unbounded_history_batches_until_five_usable_sessions(
    client,
    monkeypatch,
):
    scenario = _setup_history_beyond_limited_sessions(
        client,
        trailing_target=False,
    )

    response, loaded_batches = _capture_loaded_aggregate_batches(
        monkeypatch,
        lambda: client.post(
            f"/patients/{scenario['patient_id']}/gait/compare",
            headers=scenario["auth"],
            json={"session_ids": scenario["qualified_ids"][:2]},
        ),
    )

    assert response.status_code == 200
    history = response.get_json()["data"]["history_baselines"]["walking_speed_mps"]
    assert history == {"median": pytest.approx(1.0), "reason": None}
    assert len(loaded_batches) == 7
    assert all(len(set(batch)) <= 7 for batch in loaded_batches)
    loaded_timestamps = {
        timestamp
        for batch in loaded_batches
        for timestamp in batch
    }
    assert not loaded_timestamps.intersection(scenario["old_starts"])
    assert min(loaded_timestamps) == scenario["qualified_starts"][0]


def test_compare_preserves_requested_session_order_for_baseline(client):
    starts = [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)]
    auth, patient_id, session_ids = _setup_sessions(client, starts, walking_speeds=[0.8, 1.0])
    selected = [session_ids[1], session_ids[0]]

    response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": selected},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]
    speed_rows = data["metrics"]["walking_speed_mps"]

    assert data["session_ids"] == selected
    assert [row["session_id"] for row in speed_rows] == selected
    assert speed_rows[0]["value"] == pytest.approx(1.0)
    assert speed_rows[0]["delta_abs"] == pytest.approx(0.0)
    assert speed_rows[1]["delta_abs"] == pytest.approx(-0.2)


def test_compare_returns_recent_history_separately_from_selected_delta(client):
    starts = [_BASE_TIME + timedelta(minutes=index) for index in range(7)]
    speeds = [0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8]
    auth, patient_id, session_ids = _setup_sessions(client, starts, walking_speeds=speeds)

    response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": [session_ids[0], session_ids[1]]},
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["metrics"]["walking_speed_mps"][0]["delta_abs"] == 0.0
    assert data["history_baselines"]["walking_speed_mps"] == {
        "median": pytest.approx(1.4),
        "reason": None,
    }


def test_compare_accepts_five_sessions(client):
    starts = [_BASE_TIME + timedelta(minutes=index) for index in range(5)]
    auth, patient_id, session_ids = _setup_sessions(client, starts)

    response = client.post(
        f"/patients/{patient_id}/gait/compare",
        headers=auth,
        json={"session_ids": list(reversed(session_ids))},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["session_ids"] == list(reversed(session_ids))


def test_all_gait_workbench_routes_forbid_other_clinician(client):
    owner, patient_id, session_ids = _setup_sessions(
        client,
        [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)],
    )
    other = _create_other_clinician_auth(client)
    session_id = session_ids[0]

    responses = [
        client.get(f"/patients/{patient_id}/gait/sessions", headers=other),
        client.get(f"/patients/{patient_id}/gait/sessions/{session_id}", headers=other),
        client.get(
            f"/patients/{patient_id}/gait/sessions/{session_id}/frames",
            headers=other,
        ),
        client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=other,
            json={"session_ids": session_ids},
        ),
    ]

    assert owner["Authorization"] != other["Authorization"]
    assert [response.status_code for response in responses] == [403, 403, 403, 403]


def test_pressure_summary_detail_checks_ownership_before_raw_queries(client):
    _owner, patient_id, session_ids = _setup_sessions(client, [_BASE_TIME])
    other = _create_other_clinician_auth(client)

    response, statements = _capture_raw_selects(
        lambda: client.get(
            f"/patients/{patient_id}/gait/sessions/{session_ids[0]}",
            headers=other,
        )
    )

    assert response.status_code == 403
    assert statements == []
    assert "pressure_summary" not in response.get_data(as_text=True)


def test_workbench_payloads_exclude_unvalidated_svm(client):
    auth, patient_id, session_ids = _setup_sessions(
        client,
        [_BASE_TIME, _BASE_TIME + timedelta(minutes=1)],
    )
    session_id = session_ids[0]
    responses = [
        client.get(f"/patients/{patient_id}/gait/sessions", headers=auth),
        client.get(f"/patients/{patient_id}/gait/sessions/{session_id}", headers=auth),
        client.get(
            f"/patients/{patient_id}/gait/sessions/{session_id}/frames",
            headers=auth,
        ),
        client.post(
            f"/patients/{patient_id}/gait/compare",
            headers=auth,
            json={"session_ids": session_ids},
        ),
    ]

    for response in responses:
        assert response.status_code == 200
        payload = json.dumps(response.get_json()["data"])
        assert not any(key in payload for key in ("T1", "T2", "T3", "T4", "T5", "svm"))
