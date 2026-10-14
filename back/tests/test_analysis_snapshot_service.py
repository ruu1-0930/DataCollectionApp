"""Transactional snapshot service acceptance, using real pipeline and SQLite."""

from dataclasses import replace
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier, Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import event

from config import create_app, db
from models.models import (
    AgentSnapshotProjection, AnalysisSnapshot, ClinicalAuditEvent, Clinician,
    Device, DeviceRawData, GaitSessionRevision, IntegrationOutbox, Patient,
    SnapshotBuildAttempt, SnapshotPublicationClaim,
)
from services.analysis_snapshot import AnalysisSnapshotService, PublicationClaimRequest
from services.snapshot_repository import SnapshotError, SnapshotVersions
from services.gait_session_revision import _session_id
from services.snapshot_pipeline import SnapshotPipeline
from services.snapshot_contracts import SnapshotBuildProduct

T0 = datetime(2026, 9, 29, 0, 30)
UTC_NOW = datetime(2026, 9, 28, 16, 31, tzinfo=timezone.utc)


def seed():
    actor = Clinician(hospital="synthetic", dept="D", name="fixture", phone="0", passcode_hash="x")
    other = Clinician(hospital="synthetic", dept="D", name="other", phone="1", passcode_hash="x")
    db.session.add_all([actor, other])
    db.session.flush()
    patient = Patient(clinician_id=actor.id, subject_id="#snapshot")
    device = Device(clinician_id=actor.id, device_code="snapshot-device")
    db.session.add_all([patient, device])
    db.session.flush()
    scope = dict(actor_id=actor.id, patient_id=patient.id, device_id=device.id, other_actor=other.id)
    for second in range(4):
        for foot in ("L", "R"):
            add_row(scope, at=T0 + timedelta(seconds=second), foot=foot)
    db.session.commit()
    scope["session_id"] = _session_id(patient.id, T0)
    db.session.remove()
    return scope


def add_row(scope, *, at=T0, foot="L", accepted=None):
    row = DeviceRawData(
        clinician_id=scope["actor_id"], patient_id=scope["patient_id"],
        device_id=scope["device_id"], foot=foot, collected_at=at, uploaded_at=accepted or at,
        **{f"p{i}": 10.0 for i in range(1, 10)},
        ax=1, ay=2, az=3, gx=4, gy=5, gz=6, step_length=.6,
        walking_speed=1.2, single_support_time=.4, double_support_time=.2,
    )
    db.session.add(row)
    return row


@pytest.fixture
def scope(app):
    return seed()


def service(**kwargs):
    return AnalysisSnapshotService(clock=lambda: UTC_NOW, **kwargs)


def ensure(svc, scope):
    return svc.ensure_snapshot(**{k: scope[k] for k in ("actor_id", "patient_id", "session_id")})


def read(svc, scope, snapshot_id, projection=False):
    method = svc.get_projection if projection else svc.get_snapshot
    return method(actor_id=scope["actor_id"], patient_id=scope["patient_id"], snapshot_id=snapshot_id)


def claim(scope, snapshot_id, **kwargs):
    return PublicationClaimRequest(
        actor_id=scope["actor_id"], patient_id=scope["patient_id"],
        snapshot_id=snapshot_id, snapshot_state_version=1,
        workflow_run_id=uuid4(), candidate_hash="a" * 64, **kwargs,
    )


def test_reuse_and_external_dto_preserve_internal_hashes_and_utc_metadata(scope):
    svc = service()
    first = ensure(svc, scope)
    again = ensure(svc, scope)
    assert first.created and not again.created
    assert first.snapshot_id == again.snapshot_id
    full = read(svc, scope, first.snapshot_id).snapshot
    projection = read(svc, scope, first.snapshot_id, True).projection
    row = db.session.get(AnalysisSnapshot, str(first.snapshot_id))
    stored = json.loads(row.canonical_payload)
    assert "snapshot_id" not in stored and "state" not in stored
    assert full["content_hash"] == stored["content_hash"] == projection["snapshot_content_hash"]
    assert full["created_at"] == "2026-09-28T16:31:00.000Z"
    assert full["session"]["start_at"] == "2026-09-28T16:30:00.000Z"
    assert full["analyzer_status_reasons"] == projection["analyzer_status_reasons"]
    assert SnapshotBuildAttempt.query.count() == 1
    assert AnalysisSnapshot.query.count() == AgentSnapshotProjection.query.count() == 1
    assert {e.action for e in ClinicalAuditEvent.query.all()} >= {
        "snapshot.build", "snapshot.publish", "snapshot.read", "snapshot.projection_read",
    }


@pytest.mark.parametrize("surface", ["ensure", "full", "projection", "claim"])
def test_every_entry_enforces_patient_ownership(scope, surface):
    svc = service()
    snapshot = ensure(svc, scope)
    foreign = {**scope, "actor_id": scope["other_actor"]}
    with pytest.raises(SnapshotError, match="forbidden"):
        if surface == "ensure":
            ensure(svc, foreign)
        elif surface == "claim":
            svc.claim_publication(claim(foreign, snapshot.snapshot_id))
        else:
            read(svc, foreign, snapshot.snapshot_id, surface == "projection")


def test_claim_exact_reuse_conflict_stale_and_actor_binding(scope):
    svc = service()
    snap = ensure(svc, scope)
    request = claim(scope, snap.snapshot_id)
    first = svc.claim_publication(request)
    again = svc.claim_publication(request)
    assert first.created and not again.created
    assert first.claim == again.claim
    with pytest.raises(SnapshotError, match="claim_conflict"):
        svc.claim_publication(replace(request, candidate_hash="b" * 64))
    with pytest.raises(SnapshotError, match="stale_snapshot"):
        svc.claim_publication(replace(request, snapshot_state_version=2))
    db.session.get(Patient, scope["patient_id"]).clinician_id = scope["other_actor"]
    db.session.commit()
    with pytest.raises(SnapshotError, match="claim_conflict"):
        svc.claim_publication(replace(request, actor_id=scope["other_actor"]))
    assert SnapshotPublicationClaim.query.count() == 1


@pytest.mark.parametrize("surface", ["full", "projection", "claim", "ensure"])
@pytest.mark.parametrize("still_collecting", [False, True])
def test_late_rows_invalidate_on_all_surfaces_even_before_quiet(scope, surface, still_collecting):
    svc = service()
    first = ensure(svc, scope)
    before = db.session.get(AnalysisSnapshot, str(first.snapshot_id)).canonical_payload
    add_row(scope, accepted=T0 + timedelta(seconds=60) if still_collecting else T0)
    db.session.commit()
    if surface == "ensure" and not still_collecting:
        newer = ensure(svc, scope)
        assert newer.snapshot_id != first.snapshot_id
    else:
        expected = "stale_snapshot" if surface == "claim" else (
            "collection_in_progress" if surface == "ensure" else "snapshot_superseded")
        with pytest.raises(SnapshotError, match=expected):
            if surface == "claim":
                svc.claim_publication(claim(scope, first.snapshot_id))
            elif surface == "ensure":
                ensure(svc, scope)
            else:
                read(svc, scope, first.snapshot_id, surface == "projection")
    db.session.expire_all()
    old = db.session.get(AnalysisSnapshot, str(first.snapshot_id))
    assert old.state == "superseded" and old.state_version == 2
    assert old.canonical_payload == before
    assert IntegrationOutbox.query.count() == 1
    assert ClinicalAuditEvent.query.filter_by(action="snapshot.superseded").count() == 1


def test_failed_analyzer_is_durable_sanitized_and_explicit_retry_builds_new_attempt(scope):
    class Broken:
        def build_from_revision(self, revision):
            raise RuntimeError("secret patient name raw p1=123")
    svc = service(pipeline=Broken())
    with pytest.raises(SnapshotError, match="snapshot_unavailable"):
        ensure(svc, scope)
    attempt = SnapshotBuildAttempt.query.one()
    assert attempt.state == "failed" and attempt.error_message == "Snapshot analysis could not complete."
    assert AnalysisSnapshot.query.count() == AgentSnapshotProjection.query.count() == 0
    assert "secret" not in " ".join(e.canonical_payload for e in ClinicalAuditEvent.query.all())
    ensure(service(), scope)
    db.session.expire_all()
    assert [(a.attempt_number, a.state) for a in SnapshotBuildAttempt.query.order_by(SnapshotBuildAttempt.attempt_number)] == [(1, "failed"), (2, "succeeded")]


@pytest.mark.parametrize("failure_table", ["agent_snapshot_projection", "clinical_audit_event"])
def test_publication_failure_rolls_back_payload_and_retains_failed_attempt(scope, failure_table):
    def fail(_conn, _cursor, statement, parameters, context, _many):
        if statement.startswith("INSERT INTO " + failure_table):
            if failure_table != "clinical_audit_event" or "snapshot.publish" in parameters:
                raise RuntimeError("injected persistence failure")
    event.listen(db.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SnapshotError, match="publication_failed"):
            ensure(service(), scope)
    finally:
        event.remove(db.engine, "before_cursor_execute", fail)
    assert AnalysisSnapshot.query.count() == AgentSnapshotProjection.query.count() == 0
    assert SnapshotBuildAttempt.query.one().state == "failed"
    assert ClinicalAuditEvent.query.filter_by(action="snapshot.publish").count() == 0


def test_source_change_during_analysis_cannot_publish(scope):
    class LateArrival:
        def build_from_revision(self, revision):
            product = SnapshotPipeline().build_from_revision(revision)
            add_row(scope)
            db.session.commit()
            return product
    with pytest.raises(SnapshotError, match="session_superseded"):
        ensure(service(pipeline=LateArrival()), scope)
    assert AnalysisSnapshot.query.count() == 0
    assert SnapshotBuildAttempt.query.one().state == "failed"
    assert GaitSessionRevision.query.filter_by(state="superseded").count() == 1


def test_unsupported_projection_rejected_without_relabelling_or_analysis(scope):
    with pytest.raises(ValueError, match="unsupported_projection_version"):
        service(versions=SnapshotVersions(projection_schema_version="2"))
    assert AnalysisSnapshot.query.count() == SnapshotBuildAttempt.query.count() == 0


class VersionedTestProducer:
    """Model a separately released producer with its own declared provenance."""
    def __init__(self, versions):
        self.versions = versions

    def build_from_revision(self, revision):
        built = SnapshotPipeline().build_from_revision(revision)
        full, projection = deepcopy(built.full_snapshot), deepcopy(built.agent_projection)
        full["provenance"]["analyzer_set_version"] = self.versions.analyzer_set_version
        full["provenance"]["threshold_profile_version"] = self.versions.threshold_profile_version
        full["content_hash"] = SnapshotPipeline._hash_without(full, "content_hash")
        projection["provenance"] = deepcopy(full["provenance"])
        projection["snapshot_content_hash"] = full["content_hash"]
        projection["projection_content_hash"] = SnapshotPipeline._hash_without(projection, "projection_content_hash")
        return SnapshotBuildProduct(full, projection, built.analyzer_statuses)


def test_versioned_products_reuse_and_late_revision_supersedes_every_linked_snapshot(scope):
    first = ensure(service(), scope)
    versions = [SnapshotVersions(analyzer_set_version="producer-v2"),
                SnapshotVersions(threshold_profile_version="threshold-v2")]
    ids = {first.snapshot_id}
    for version in versions:
        svc = service(versions=version, pipeline=VersionedTestProducer(version))
        built = ensure(svc, scope)
        assert not ensure(svc, scope).created
        ids.add(built.snapshot_id)
    assert len(ids) == 3 and GaitSessionRevision.query.count() == 1
    add_row(scope)
    db.session.commit()
    replacement = ensure(service(), scope)
    db.session.expire_all()
    assert replacement.snapshot_id not in ids
    assert AnalysisSnapshot.query.filter_by(state="superseded").count() == 3
    assert IntegrationOutbox.query.count() == 3
    assert ClinicalAuditEvent.query.filter_by(action="snapshot.superseded").count() == 3


def test_sensor_analyzer_upgrade_builds_new_snapshot_without_rewriting_old(scope):
    old_versions = SnapshotVersions(analyzer_set_version="snapshot-pipeline-v1")

    class LegacyFixtureProducer(VersionedTestProducer):
        def build_from_revision(self, revision):
            product = super().build_from_revision(revision)
            full, projection = deepcopy(product.full_snapshot), deepcopy(product.agent_projection)
            for point in full["chart_series"]:
                for key in ("pressure_left_adc_decimal", "pressure_right_adc_decimal", "imu_magnitude_raw_unscaled_decimal"):
                    point[key] = None
            full["content_hash"] = SnapshotPipeline._hash_without(full, "content_hash")
            projection["snapshot_content_hash"] = full["content_hash"]
            projection["projection_content_hash"] = SnapshotPipeline._hash_without(projection, "projection_content_hash")
            return SnapshotBuildProduct(full, projection, product.analyzer_statuses)

    old = ensure(service(versions=old_versions, pipeline=LegacyFixtureProducer(old_versions)), scope)
    old_bytes = db.session.get(AnalysisSnapshot, str(old.snapshot_id)).canonical_payload
    fresh = ensure(service(), scope)
    assert fresh.created and fresh.snapshot_id != old.snapshot_id
    assert not ensure(service(), scope).created
    assert fresh.snapshot["chart_series"][0]["pressure_left_adc_decimal"] == "10.000000"
    db.session.expire_all()
    assert db.session.get(AnalysisSnapshot, str(old.snapshot_id)).canonical_payload == old_bytes
    assert read(service(), scope, old.snapshot_id).snapshot["chart_series"][0]["pressure_left_adc_decimal"] is None
    assert AnalysisSnapshot.query.count() == 2 and GaitSessionRevision.query.count() == 1


def test_requested_version_cannot_relabel_default_pipeline(scope):
    with pytest.raises(SnapshotError, match="publication_failed"):
        ensure(service(versions=SnapshotVersions(analyzer_set_version="imaginary")), scope)
    assert AnalysisSnapshot.query.count() == 0
    assert SnapshotBuildAttempt.query.one().state == "failed"


def test_claim_audit_failure_rolls_back_claim(scope):
    svc = service()
    snap = ensure(svc, scope)
    def fail(_conn, _cursor, statement, parameters, _context, _many):
        if statement.startswith("INSERT INTO clinical_audit_event") and "snapshot.claim" in parameters:
            raise RuntimeError("sensitive driver parameters")
    event.listen(db.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SnapshotError, match="publication_failed") as caught:
            svc.claim_publication(claim(scope, snap.snapshot_id))
        assert "sensitive" not in str(caught.value)
    finally:
        event.remove(db.engine, "before_cursor_execute", fail)
    assert SnapshotPublicationClaim.query.count() == 0


def test_late_invalidation_outbox_failure_rolls_back_revision_and_all_products(scope):
    svc = service()
    snapshot = ensure(svc, scope)
    add_row(scope)
    db.session.commit()
    def fail(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO integration_outbox"):
            raise RuntimeError("injected failure")
    event.listen(db.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(SnapshotError, match="publication_failed"):
            read(svc, scope, snapshot.snapshot_id)
    finally:
        event.remove(db.engine, "before_cursor_execute", fail)
    db.session.expire_all()
    assert GaitSessionRevision.query.count() == 1
    assert GaitSessionRevision.query.one().state == "closed_by_inactivity"
    assert AnalysisSnapshot.query.one().state == "published"
    assert AnalysisSnapshot.query.one().state_version == 1
    assert ClinicalAuditEvent.query.filter_by(action="snapshot.superseded").count() == 0
    assert ClinicalAuditEvent.query.filter_by(action="session.superseded").count() == 0
    assert IntegrationOutbox.query.count() == 0
    with pytest.raises(SnapshotError, match="snapshot_superseded"):
        read(svc, scope, snapshot.snapshot_id)


@pytest.mark.parametrize("value", [0, True, "1", None])
def test_invalid_actor_scope_is_rejected(scope, value):
    with pytest.raises(SnapshotError, match="invalid_request"):
        ensure(service(), {**scope, "actor_id": value})


@pytest.mark.parametrize("updates", [
    {"candidate_hash": "Patient name"}, {"snapshot_state_version": True},
    {"workflow_run_id": "00000000-0000-0000-0000-000000000000"},
])
def test_invalid_claim_has_safe_error(scope, updates):
    snap = ensure(service(), scope)
    with pytest.raises(SnapshotError, match="invalid_request"):
        service().claim_publication(replace(claim(scope, snap.snapshot_id), **updates))


def test_file_sqlite_separate_sessions_race_yields_one_analyzer_and_auditable_building(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "race.db")})
    with app.app_context():
        db.create_all()
        scope = seed()
    entered, release = Event(), Event()
    calls, outcomes = [], []
    class Slow:
        def build_from_revision(self, revision):
            calls.append(revision.id)
            entered.set()
            assert release.wait(10)
            return SnapshotPipeline().build_from_revision(revision)
    def build():
        with app.app_context():
            try:
                outcomes.append(ensure(service(pipeline=Slow()), scope))
            except Exception as exc:
                outcomes.append(exc)
    thread = Thread(target=build)
    thread.start()
    try:
        assert entered.wait(10)
        with app.app_context():
            with pytest.raises(SnapshotError, match="snapshot_building") as caught:
                ensure(service(), scope)
            assert caught.value.details["retry_after_ms"] > 0
            assert SnapshotBuildAttempt.query.one().state == "running"
            assert ClinicalAuditEvent.query.filter_by(result="snapshot_building").count() == 1
            assert AnalysisSnapshot.query.count() == 0
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive() and len(calls) == 1
    assert len(outcomes) == 1 and not isinstance(outcomes[0], Exception), outcomes
    with app.app_context():
        assert AnalysisSnapshot.query.count() == AgentSnapshotProjection.query.count() == 1
        assert not ensure(service(), scope).created
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def test_file_sqlite_claim_race_one_candidate_wins(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "test", "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "claim-race.db")})
    with app.app_context():
        db.create_all()
        scope = seed()
        snap = ensure(service(), scope)
        request = claim(scope, snap.snapshot_id)
    gate, outcomes = Barrier(2), []
    def claim_candidate(candidate_hash):
        with app.app_context():
            gate.wait(timeout=10)
            try:
                outcomes.append(service().claim_publication(replace(request, candidate_hash=candidate_hash)))
            except SnapshotError as exc:
                outcomes.append(exc.code)
    threads = [Thread(target=claim_candidate, args=(value * 64,)) for value in ("a", "b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()
    assert len(outcomes) == 2 and outcomes.count("claim_conflict") == 1
    with app.app_context():
        assert SnapshotPublicationClaim.query.count() == 1
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
