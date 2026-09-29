from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from config import db
from models.models import Clinician, Device, DeviceRawData, GaitSessionRevision, Patient
from services.gait_session_revision import (
    GaitSessionRevisionService,
    SessionResolutionError,
    _session_id,
    raw_rows_fingerprint,
)


T0 = datetime(2026, 9, 29, 9, 0, 0, 123456)


@pytest.fixture
def revision_scope(app):
    clinician = Clinician(
        hospital="synthetic", dept="D", name="fixture", phone="0", passcode_hash="x"
    )
    db.session.add(clinician)
    db.session.flush()
    patient = Patient(clinician_id=clinician.id, subject_id="#session-one")
    other_patient = Patient(clinician_id=clinician.id, subject_id="#session-two")
    device = Device(clinician_id=clinician.id, device_code="device-one")
    other_device = Device(clinician_id=clinician.id, device_code="device-two")
    db.session.add_all([patient, other_patient, device, other_device])
    db.session.commit()
    return {
        "clinician": clinician,
        "patient": patient,
        "other_patient": other_patient,
        "device": device,
        "other_device": other_device,
    }


def _raw(scope, *, at, accepted_at=None, foot="L", patient=None, device=None, pressure=1.0):
    row = DeviceRawData(
        clinician_id=scope["clinician"].id,
        patient_id=(patient or scope["patient"]).id,
        device_id=(device or scope["device"]).id,
        foot=foot,
        **{f"p{index}": pressure for index in range(1, 10)},
        ax=1.123456789,
        ay=2.0,
        az=3.0,
        gx=4.0,
        gy=5.0,
        gz=6.0,
        step_length=0.6000001,
        walking_speed=1.1000001,
        single_support_time=0.4000001,
        double_support_time=0.2000001,
        collected_at=at,
        uploaded_at=accepted_at or at,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _resolve(scope, *, now, session_start=T0):
    return GaitSessionRevisionService().resolve_closed_revision(
        patient_id=scope["patient"].id,
        session_id=_session_id(scope["patient"].id, session_start),
        now=now,
    )


def test_latest_session_closes_only_after_more_than_thirty_seconds_of_device_quiet(revision_scope):
    _raw(revision_scope, at=T0, accepted_at=T0)

    with pytest.raises(SessionResolutionError, match="collection_in_progress"):
        _resolve(revision_scope, now=T0 + timedelta(seconds=29, microseconds=999999))

    result = _resolve(revision_scope, now=T0 + timedelta(seconds=30))
    assert result.revision.state == "closed_by_inactivity"
    assert result.revision.row_count == 1
    assert result.closure_evidence.idle_seconds == result.closure_evidence.idle_seconds.__class__("30")


def test_historical_gap_closes_even_without_a_later_quiet_period(revision_scope):
    first = _raw(revision_scope, at=T0, accepted_at=T0)
    _raw(revision_scope, at=T0 + timedelta(seconds=31), accepted_at=T0 + timedelta(seconds=31))

    result = _resolve(revision_scope, now=T0 + timedelta(seconds=32))

    assert result.revision.first_row_id == first.id
    assert result.revision.state == "closed_by_inactivity"
    assert result.closure_evidence.reason == "later_accepted_row_gap"


def test_repeated_resolution_reuses_the_same_closed_revision(revision_scope):
    _raw(revision_scope, at=T0)

    first = _resolve(revision_scope, now=T0 + timedelta(seconds=31))
    second = _resolve(revision_scope, now=T0 + timedelta(seconds=32))

    assert first.revision.id == second.revision.id
    assert second.closure_evidence == first.closure_evidence
    assert GaitSessionRevision.query.count() == 1


def test_order_and_duplicate_rows_change_the_fingerprint_and_supersede(revision_scope):
    first = _raw(revision_scope, at=T0, foot="L", pressure=1.0)
    second = _raw(revision_scope, at=T0, foot="R", pressure=2.0)
    original = _resolve(revision_scope, now=T0 + timedelta(seconds=31))

    duplicate = _raw(
        revision_scope,
        at=T0,
        accepted_at=T0 + timedelta(seconds=31),
        foot="L",
        pressure=1.0,
    )
    replacement = _resolve(revision_scope, now=T0 + timedelta(seconds=61))

    assert original.revision.state == "superseded"
    assert original.revision.superseded_by_revision_id == replacement.revision.id
    assert replacement.revision.revision == 2
    assert replacement.revision.ordered_row_ids_canonical == f"[{first.id},{second.id},{duplicate.id}]"
    assert replacement.raw_data_fingerprint != original.raw_data_fingerprint


def test_raw_fingerprint_tags_nonfinite_values_before_snapshot_filtering():
    base = {
        "id": 1,
        "foot": "L",
        "collected_at": T0,
        "uploaded_at": T0,
        **{f"p{index}": 1.0 for index in range(1, 10)},
        "ax": 1.0, "ay": 2.0, "az": 3.0, "gx": 4.0, "gy": 5.0, "gz": 6.0,
        "step_length": 0.6, "walking_speed": 1.1,
        "single_support_time": 0.4, "double_support_time": 0.2,
    }
    nan = dict(base, walking_speed=float("nan"))
    positive_infinity = dict(base, walking_speed=float("inf"))

    nan_hash = raw_rows_fingerprint(
        patient_id=1, device_id=2, session_id="synthetic", rows=[nan]
    )
    infinity_hash = raw_rows_fingerprint(
        patient_id=1, device_id=2, session_id="synthetic", rows=[positive_infinity]
    )
    changed_value_hash = raw_rows_fingerprint(
        patient_id=1, device_id=2, session_id="synthetic", rows=[dict(base, p1=2.0)]
    )

    assert nan_hash != infinity_hash
    assert changed_value_hash != nan_hash


def test_invalid_or_cross_patient_session_id_queries_no_raw_rows(revision_scope):
    service = GaitSessionRevisionService()
    statements = []

    def record(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "device_raw_data" in statement:
            statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", record)
    try:
        with pytest.raises(SessionResolutionError, match="invalid_session_id"):
            service.resolve_closed_revision(
                patient_id=revision_scope["patient"].id,
                session_id=_session_id(revision_scope["other_patient"].id, T0),
                now=T0,
            )
    finally:
        event.remove(db.engine, "before_cursor_execute", record)

    assert statements == []


def test_multi_device_legacy_range_fails_closed_instead_of_dropping_rows(revision_scope):
    _raw(revision_scope, at=T0)
    _raw(revision_scope, at=T0 + timedelta(seconds=1), device=revision_scope["other_device"])

    with pytest.raises(SessionResolutionError, match="scope_mismatch"):
        _resolve(revision_scope, now=T0 + timedelta(seconds=31))


def test_same_device_activity_for_another_patient_prevents_quiet_close(revision_scope):
    _raw(revision_scope, at=T0, accepted_at=T0)
    _raw(
        revision_scope,
        patient=revision_scope["other_patient"],
        at=T0 + timedelta(seconds=1),
        accepted_at=T0 + timedelta(seconds=29),
    )

    with pytest.raises(SessionResolutionError, match="collection_in_progress"):
        _resolve(revision_scope, now=T0 + timedelta(seconds=31))
