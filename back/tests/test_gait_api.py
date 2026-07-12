"""Integration tests for the stable gait data workbench API."""

import json
import re
from datetime import datetime, timedelta

import pytest

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
            "phone": "1",
            "terminal_code": "t",
            "passcode": "1234",
        },
    ).get_json()["data"]["token"]
    auth = {"Authorization": f"Bearer {token}"}
    patient_id = client.post(
        "/patients",
        headers=auth,
        json={"name": "A", "phone": "111", "age": 72},
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


def _create_other_clinician_auth(client):
    token = client.post(
        "/clinician/enable",
        json={
            "hospital": "H",
            "dept": "D",
            "name": "Dr2",
            "phone": "2",
            "terminal_code": "t2",
            "passcode": "1234",
        },
    ).get_json()["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


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
