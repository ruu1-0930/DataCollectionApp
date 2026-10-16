"""Immutable products and publication metadata under a database scope lock.

Each transaction uses a new Session. SQLite uses BEGIN IMMEDIATE; InnoDB uses
READ COMMITTED and a patient FOR UPDATE lock. The latter also fences ordinary
raw INSERTs via their enforced patient FK. All service writers take this lock.
Analysis runs outside the transaction; its durable attempt reserves the identity.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import db
from access import AccessError, load_account_context, require_patient_scope
from models.models import (
    AgentSnapshotProjection, AnalysisSnapshot, DeviceRawData, GaitSessionRevision,
    IntegrationOutbox, Patient, SnapshotBuildAttempt,
)
from services.canonical_json import canonical_json_bytes, sha256_hex
from services.clinical_audit import utc_naive, utc_text, write_audit
from services.snapshot_contracts import SNAPSHOT_ANALYZER_SET_VERSION, _validator, validate_build_product


class SnapshotError(RuntimeError):
    def __init__(self, code, *, details=None, trace_id=None):
        super().__init__(code)
        self.code, self.details, self.trace_id = code, details or {}, trace_id


@dataclass(frozen=True)
class SnapshotVersions:
    snapshot_schema_version: str = "1"
    analyzer_set_version: str = SNAPSHOT_ANALYZER_SET_VERSION
    threshold_profile_version: str = "pressure_asymmetry_research_v1"
    projection_schema_version: str = "1"


@dataclass(frozen=True)
class SnapshotIdentity:
    patient_id: int
    session_revision_id: str
    raw_data_fingerprint: str
    snapshot_schema_version: str
    analyzer_set_version: str
    threshold_profile_version: str

    @property
    def fingerprint(self):
        return sha256_hex(canonical_json_bytes(asdict(self)))


class AnalysisSnapshotRepository:
    def __init__(self, engine=None, *, session=None):
        self.engine = engine if engine is not None else db.engine
        self.session = session

    @contextmanager
    def transaction(self, *, actor_id, patient_id, authorize=True):
        # No reuse of request Session or repeatable-read view across publication fences.
        with self.engine.connect() as connection:
            if connection.dialect.name == "mysql":
                connection = connection.execution_options(isolation_level="READ COMMITTED")
            elif connection.dialect.name != "sqlite":
                raise RuntimeError("unsupported_snapshot_database")
            with Session(bind=connection, expire_on_commit=False) as session:
                try:
                    if connection.dialect.name == "sqlite":
                        session.execute(text("PRAGMA foreign_keys=ON"))
                        session.execute(text("BEGIN IMMEDIATE"))
                    patient = session.query(Patient).filter_by(id=patient_id).with_for_update().one_or_none()
                    if patient is None:
                        raise SnapshotError("patient_not_found")
                    if authorize:
                        try:
                            account = load_account_context(actor_id, session=session)
                            require_patient_scope(account, owner_id=patient.clinician_id, capability='snapshot.execute')
                        except AccessError:
                            raise SnapshotError("forbidden") from None
                    yield AnalysisSnapshotRepository(self.engine, session=session)
                    session.commit()
                except BaseException:
                    session.rollback()
                    raise

    def snapshot(self, snapshot_id, patient_id):
        row = self.session.query(AnalysisSnapshot).filter_by(id=str(snapshot_id), patient_id=patient_id).one_or_none()
        if row is None:
            raise SnapshotError("snapshot_not_found")
        return row

    def identity_snapshot(self, identity):
        return self.session.query(AnalysisSnapshot).filter_by(**asdict(identity)).one_or_none()

    def reserve(self, identity, *, actor_id, trace_id, now):
        latest = (self.session.query(SnapshotBuildAttempt)
                  .filter_by(identity_fingerprint=identity.fingerprint)
                  .order_by(SnapshotBuildAttempt.attempt_number.desc()).first())
        if latest is not None and latest.state in {"pending", "running"}:
            return latest, False
        attempt = SnapshotBuildAttempt(
            id=str(uuid4()), identity_fingerprint=identity.fingerprint,
            attempt_number=latest.attempt_number + 1 if latest else 1,
            state="pending", trace_id=trace_id, created_at=utc_naive(now),
        )
        self.session.add(attempt)
        self.session.flush()
        attempt.state, attempt.started_at = "running", utc_naive(now)
        write_audit(self.session, actor_id=actor_id, patient_id=identity.patient_id,
                    session_revision_id=identity.session_revision_id, trace_id=trace_id,
                    action="snapshot.build", result="running", now=now,
                    details={"attempt_id": attempt.id, "attempt_number": attempt.attempt_number,
                             "identity_fingerprint": identity.fingerprint})
        return attempt, True

    def publish(self, product, identity, versions, *, actor_id, attempt_id, trace_id, now):
        full, projection = dict(product.full_snapshot), dict(product.agent_projection)
        validate_build_product(full_snapshot=full, agent_projection=projection)
        # Version changes require a real producer, never a relabelled old payload.
        actual = SnapshotIdentity(full["patient_id"], full["session_revision_id"],
                                  full["session"]["raw_data_fingerprint"],
                                  full["provenance"]["snapshot_schema_version"],
                                  full["provenance"]["analyzer_set_version"],
                                  full["provenance"]["threshold_profile_version"])
        shared = {key: full[key] for key in projection if key in full}
        if (actual != identity or full["schema_version"] != identity.snapshot_schema_version
                or projection["projection_schema_version"] != versions.projection_schema_version
                or any(projection[key] != value for key, value in shared.items())
                or projection["snapshot_content_hash"] != full["content_hash"]):
            raise SnapshotError("internal_invariant_failed")
        for payload, field in ((full, "content_hash"), (projection, "projection_content_hash")):
            if payload[field] != sha256_hex(canonical_json_bytes({k: v for k, v in payload.items() if k != field})):
                raise SnapshotError("internal_invariant_failed")
        revision = self.session.get(GaitSessionRevision, identity.session_revision_id)
        if revision.state != "closed_by_inactivity" or full["session_id"] != revision.session_key:
            raise SnapshotError("session_superseded")
        attempt = self.session.get(SnapshotBuildAttempt, attempt_id)
        if attempt.state != "running" or attempt.identity_fingerprint != identity.fingerprint or attempt.trace_id != trace_id:
            raise SnapshotError("internal_invariant_failed")
        row = AnalysisSnapshot(
            id=str(uuid4()), **asdict(identity), identity_fingerprint=identity.fingerprint,
            canonical_payload=canonical_json_bytes(full).decode(), content_hash=full["content_hash"],
            state="published", state_version=1, created_at=utc_naive(now), published_at=utc_naive(now),
        )
        self.session.add(row)
        self.session.flush()
        child = AgentSnapshotProjection(
            snapshot_id=row.id, projection_schema_version=versions.projection_schema_version,
            canonical_payload=canonical_json_bytes(projection).decode(),
            content_hash=projection["projection_content_hash"], created_at=utc_naive(now),
        )
        self.session.add(child)
        self.session.flush()
        self.full_dto(row)
        self.projection_dto(row, versions.projection_schema_version)
        attempt.state, attempt.finished_at = "succeeded", utc_naive(now)
        write_audit(self.session, actor_id=actor_id, patient_id=row.patient_id, snapshot_id=row.id,
                    session_revision_id=row.session_revision_id, trace_id=trace_id,
                    action="snapshot.publish", result="succeeded", now=now,
                    details={"attempt_id": attempt_id, "content_hash": row.content_hash})
        return row

    def supersede(self, row, *, actor_id, trace_id, now, replacement=None):
        if replacement is not None:
            old_revision = self.session.get(GaitSessionRevision, row.session_revision_id)
            new_revision = self.session.get(GaitSessionRevision, replacement.session_revision_id)
            if (replacement.id == row.id or replacement.patient_id != row.patient_id
                    or replacement.state != "published" or old_revision.session_key != new_revision.session_key):
                raise SnapshotError("internal_invariant_failed")
        if row.state == "superseded":
            return
        if row.state != "published":
            raise SnapshotError("internal_invariant_failed")
        row.state, row.state_version, row.superseded_at = "superseded", row.state_version + 1, utc_naive(now)
        row.superseded_by_snapshot_id = replacement.id if replacement else None
        payload = dict(snapshot_id=row.id, patient_id=row.patient_id,
                       snapshot_state_version=row.state_version, superseded_by=row.superseded_by_snapshot_id)
        canonical = canonical_json_bytes(payload)
        self.session.add(IntegrationOutbox(
            event_type="snapshot.superseded", event_version="1", snapshot_id=row.id,
            patient_id=row.patient_id, state_version=row.state_version,
            canonical_payload=canonical.decode(), content_hash=sha256_hex(canonical), created_at=utc_naive(now),
        ))
        write_audit(self.session, actor_id=actor_id, patient_id=row.patient_id, snapshot_id=row.id,
                    session_revision_id=row.session_revision_id, trace_id=trace_id,
                    action="snapshot.superseded", result="ok", now=now,
                    details={"snapshot_state_version": row.state_version, **(
                        {"replacement_snapshot_id": replacement.id} if replacement else {})})

    def full_dto(self, row):
        payload = json.loads(row.canonical_payload)
        payload.update(snapshot_id=row.id, state=row.state, snapshot_state_version=row.state_version,
                       created_at=utc_text(row.created_at))
        _validator("AnalysisSnapshotV1").validate(payload)
        return payload

    def projection_dto(self, row, version):
        child = self.session.get(AgentSnapshotProjection, (row.id, version))
        if child is None:
            raise SnapshotError("snapshot_unavailable")
        payload = json.loads(child.canonical_payload)
        payload.update(snapshot_id=row.id, snapshot_state_version=row.state_version)
        _validator("AgentSnapshotProjectionV1").validate(payload)
        return payload

    def status_dto(self, row):
        payload = dict(snapshot_id=row.id, state=row.state,
                       snapshot_state_version=row.state_version, content_hash=row.content_hash,
                       superseded_by=row.superseded_by_snapshot_id)
        _validator("SnapshotStatusV1").validate(payload)
        return payload

    def load_revision_rows(self, revision):
        with Session(self.engine) as session:
            return session.query(DeviceRawData).filter(
                DeviceRawData.patient_id == revision.patient_id,
                DeviceRawData.device_id == revision.device_id,
                DeviceRawData.id.in_(json.loads(revision.ordered_row_ids_canonical)),
            ).order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc()).all()
