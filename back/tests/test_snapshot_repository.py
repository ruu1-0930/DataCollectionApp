"""Repository identity, rollback, immutability, and replacement scope contracts."""

from dataclasses import replace
import json
from uuid import uuid4

import pytest
from sqlalchemy import event

from config import db
from models.models import AnalysisSnapshot, ClinicalAuditEvent, IntegrationOutbox
from services.snapshot_repository import SnapshotIdentity, SnapshotError
from .test_analysis_snapshot_service import (
    scope, service, ensure, UTC_NOW, VersionedTestProducer, add_row, T0,
)


@pytest.mark.parametrize("field,value", [
    ("patient_id", 2), ("session_revision_id", str(uuid4())),
    ("raw_data_fingerprint", "b" * 64), ("snapshot_schema_version", "2"),
    ("analyzer_set_version", "analyzer-v2"), ("threshold_profile_version", "threshold-v2"),
])
def test_all_six_identity_fields_affect_key(field, value):
    identity = SnapshotIdentity(1, str(uuid4()), "a" * 64, "1", "analyzer-v1", "threshold-v1")
    assert replace(identity, **{field: value}).fingerprint != identity.fingerprint
    assert replace(identity).fingerprint == identity.fingerprint
    assert "projection_schema_version" not in identity.__dataclass_fields__


@pytest.mark.parametrize("failure_table", ["clinical_audit_event", "integration_outbox"])
def test_supersession_state_audit_outbox_rollback_as_one_transaction(scope, failure_table):
    svc = service()
    snapshot = ensure(svc, scope)
    initial_audits = ClinicalAuditEvent.query.count()
    db.session.remove()
    def fail(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("INSERT INTO " + failure_table):
            raise RuntimeError("injected source transaction failure")
    event.listen(db.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
                row = repo.snapshot(snapshot.snapshot_id, scope["patient_id"])
                repo.supersede(row, actor_id=scope["actor_id"], trace_id=str(uuid4()), now=UTC_NOW)
    finally:
        event.remove(db.engine, "before_cursor_execute", fail)
    row = db.session.get(AnalysisSnapshot, str(snapshot.snapshot_id))
    assert row.state == "published" and row.state_version == 1 and row.superseded_at is None
    assert ClinicalAuditEvent.query.count() == initial_audits
    assert IntegrationOutbox.query.count() == 0


def test_supersession_once_preserves_hash_and_rejects_self_replacement(scope):
    svc = service()
    result = ensure(svc, scope)
    original = db.session.get(AnalysisSnapshot, str(result.snapshot_id)).canonical_payload
    db.session.remove()
    with pytest.raises(SnapshotError, match="internal_invariant_failed"):
        with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
            row = repo.snapshot(result.snapshot_id, scope["patient_id"])
            repo.supersede(row, actor_id=scope["actor_id"], trace_id=str(uuid4()), now=UTC_NOW, replacement=row)
    for _ in range(2):
        with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
            row = repo.snapshot(result.snapshot_id, scope["patient_id"])
            repo.supersede(row, actor_id=scope["actor_id"], trace_id=str(uuid4()), now=UTC_NOW)
    row = db.session.get(AnalysisSnapshot, str(result.snapshot_id))
    assert row.state_version == 2 and row.canonical_payload == original
    assert IntegrationOutbox.query.count() == 1
    assert json.loads(IntegrationOutbox.query.one().canonical_payload)["snapshot_state_version"] == 2


def test_audit_hash_chain_and_whitelist(scope):
    from services.clinical_audit import write_audit
    from services.canonical_json import canonical_json_bytes, sha256_hex
    svc = service()
    ensure(svc, scope)
    records = ClinicalAuditEvent.query.order_by(ClinicalAuditEvent.created_at).all()
    previous = None
    for record in records:
        body = json.loads(record.canonical_payload)
        assert record.previous_event_hash == previous
        assert body["previous_event_hash"] == previous
        assert record.event_hash == sha256_hex(canonical_json_bytes(body))
        previous = record.event_hash
    with pytest.raises(ValueError, match="unsafe_audit"):
        with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
            write_audit(repo.session, actor_id=scope["actor_id"], patient_id=scope["patient_id"],
                        trace_id=str(uuid4()), action="snapshot.read", result="ok", now=UTC_NOW,
                        details={"patient_name": "never persist"})


def test_replacement_reference_is_same_patient_same_session_published(scope):
    from services.snapshot_repository import SnapshotVersions
    version = SnapshotVersions(analyzer_set_version="replacement-producer")
    svc = service()
    first = ensure(svc, scope)
    second = ensure(service(versions=version, pipeline=VersionedTestProducer(version)), scope)
    with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
        old = repo.snapshot(first.snapshot_id, scope["patient_id"])
        new = repo.snapshot(second.snapshot_id, scope["patient_id"])
        repo.supersede(old, actor_id=scope["actor_id"], trace_id=str(uuid4()), now=UTC_NOW, replacement=new)
    old = db.session.get(AnalysisSnapshot, str(first.snapshot_id))
    assert old.superseded_by_snapshot_id == str(second.snapshot_id)
    assert old.state_version == 2
    assert json.loads(IntegrationOutbox.query.one().canonical_payload)["superseded_by"] == str(second.snapshot_id)


@pytest.mark.parametrize("different", ["patient", "session"])
def test_cross_scope_replacement_is_rejected(scope, different):
    from datetime import timedelta
    from models.models import Patient
    from services.gait_session_revision import _session_id
    svc = service()
    first = ensure(svc, scope)
    other = dict(scope)
    at = T0 - timedelta(seconds=60)
    if different == "patient":
        patient = Patient(clinician_id=scope["actor_id"], subject_id="#other-snapshot")
        db.session.add(patient)
        db.session.flush()
        other["patient_id"] = patient.id
        at = T0
    add_row(other, at=at)
    db.session.commit()
    other["session_id"] = _session_id(other["patient_id"], at)
    second = ensure(svc, other)
    with pytest.raises(SnapshotError, match="internal_invariant_failed"):
        with svc.repository.transaction(actor_id=scope["actor_id"], patient_id=scope["patient_id"]) as repo:
            old = repo.snapshot(first.snapshot_id, scope["patient_id"])
            new = repo.snapshot(second.snapshot_id, other["patient_id"])
            repo.supersede(old, actor_id=scope["actor_id"], trace_id=str(uuid4()), now=UTC_NOW, replacement=new)
    assert IntegrationOutbox.query.count() == 0
