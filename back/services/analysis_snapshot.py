"""Ownership-enforced snapshot orchestration with transactional publication fences."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import wraps
import re
from uuid import UUID, uuid4

from models.models import AnalysisSnapshot, GaitSessionRevision, SnapshotBuildAttempt, SnapshotPublicationClaim
from services.clinical_audit import utc_naive, utc_text, write_audit
from services.gait_session_revision import GaitSessionRevisionService, SessionResolutionError
from services.snapshot_contracts import _validator
from services.snapshot_pipeline import SnapshotPipeline
from services.snapshot_repository import AnalysisSnapshotRepository, SnapshotError, SnapshotIdentity, SnapshotVersions


def _safe_boundary(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except SnapshotError:
            raise
        except Exception:
            # Driver/validation exceptions may contain bound SQL parameters or PHI.
            raise SnapshotError("publication_failed") from None
    return wrapped


def _scope(actor_id, patient_id):
    if type(actor_id) is not int or type(patient_id) is not int or min(actor_id, patient_id) < 1:
        raise SnapshotError("invalid_request")


def _uuid(value):
    value = str(value)
    if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", value):
        raise SnapshotError("invalid_request")
    return value


@dataclass(frozen=True)
class EnsureSnapshotResult:
    snapshot_id: UUID
    created: bool
    snapshot: dict


@dataclass(frozen=True)
class SnapshotReadResult:
    snapshot: dict


@dataclass(frozen=True)
class SnapshotStatusResult:
    status: dict


@dataclass(frozen=True)
class ProjectionReadResult:
    projection: dict


@dataclass(frozen=True)
class PublicationClaimRequest:
    actor_id: int
    patient_id: int
    snapshot_id: UUID
    snapshot_state_version: int
    workflow_run_id: UUID
    candidate_hash: str


@dataclass(frozen=True)
class PublicationClaimResult:
    claim: dict
    created: bool


class AnalysisSnapshotService:
    def __init__(self, *, repository=None, pipeline=None, versions=None, clock=None):
        self.repository = repository if repository is not None else AnalysisSnapshotRepository()
        self.versions = versions or SnapshotVersions()
        if self.versions.projection_schema_version != "1":
            raise ValueError("unsupported_projection_version")
        if self.versions.snapshot_schema_version != "1":
            raise ValueError("unsupported_snapshot_version")
        self.pipeline = pipeline if pipeline is not None else SnapshotPipeline(row_loader=self.repository.load_revision_rows)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _identity(self, resolved):
        return SnapshotIdentity(
            resolved.revision.patient_id, resolved.revision.id, resolved.raw_data_fingerprint,
            self.versions.snapshot_schema_version, self.versions.analyzer_set_version,
            self.versions.threshold_profile_version,
        )

    def _refresh(self, repo, *, actor_id, patient_id, session_id, trace_id):
        """Commit invalidation even when a changed session cannot yet close again."""
        now = self.clock()
        source_now = now.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
        resolver = GaitSessionRevisionService(session=repo.session)
        previously_closed = repo.session.query(GaitSessionRevision).filter_by(
            patient_id=patient_id, session_key=session_id, state="closed_by_inactivity").all()
        error, resolved = None, None
        try:
            resolved = resolver.resolve_closed_revision(patient_id=patient_id, session_id=session_id, now=source_now)
        except SessionResolutionError as exc:
            code = str(exc)
            error = SnapshotError("invalid_request" if code == "invalid_session_id" else code, trace_id=trace_id)
            if code in {"collection_in_progress", "session_not_found", "scope_mismatch"}:
                revisions = repo.session.query(GaitSessionRevision).filter_by(
                    patient_id=patient_id, session_key=session_id, state="closed_by_inactivity").all()
                for revision in revisions:
                    revision.state = "superseded"
        repo.session.flush()
        for revision in previously_closed:
            if revision.state == "superseded":
                write_audit(repo.session, actor_id=actor_id, patient_id=patient_id,
                            session_revision_id=revision.id, trace_id=trace_id,
                            action="session.superseded", result="ok", now=now)
        stale = repo.session.query(AnalysisSnapshot).join(
            GaitSessionRevision, AnalysisSnapshot.session_revision_id == GaitSessionRevision.id
        ).filter(
            GaitSessionRevision.patient_id == patient_id, GaitSessionRevision.session_key == session_id,
            GaitSessionRevision.state == "superseded", AnalysisSnapshot.state == "published",
        ).all()
        for snapshot in stale:
            repo.supersede(snapshot, actor_id=actor_id, trace_id=trace_id, now=now)
        return resolved, error

    @_safe_boundary
    def ensure_snapshot(self, *, actor_id: int, patient_id: int, session_id: str) -> EnsureSnapshotResult:
        _scope(actor_id, patient_id)
        if not isinstance(session_id, str):
            raise SnapshotError("invalid_request")
        trace_id, error, result = str(uuid4()), None, None
        with self.repository.transaction(actor_id=actor_id, patient_id=patient_id) as repo:
            resolved, error = self._refresh(repo, actor_id=actor_id, patient_id=patient_id,
                                            session_id=session_id, trace_id=trace_id)
            if error is None:
                identity = self._identity(resolved)
                existing = repo.identity_snapshot(identity)
                if existing is not None:
                    if existing.state != "published":
                        error = SnapshotError("snapshot_superseded", trace_id=trace_id)
                    else:
                        result = EnsureSnapshotResult(UUID(existing.id), False, repo.full_dto(existing))
                        write_audit(repo.session, actor_id=actor_id, patient_id=patient_id,
                                    snapshot_id=existing.id, trace_id=trace_id, action="snapshot.build",
                                    result="reused", now=self.clock())
                else:
                    attempt, acquired = repo.reserve(identity, actor_id=actor_id, trace_id=trace_id, now=self.clock())
                    if not acquired:
                        error = SnapshotError("snapshot_building", trace_id=trace_id,
                                              details={"attempt_id": attempt.id, "retry_after_ms": 250})
                        write_audit(repo.session, actor_id=actor_id, patient_id=patient_id,
                                    trace_id=trace_id, action="snapshot.build", result="snapshot_building",
                                    now=self.clock(), details={"attempt_id": attempt.id})
                    else:
                        attempt_id, revision = attempt.id, resolved.revision
        if error is not None:
            raise error
        if result is not None:
            return result
        try:
            product = self.pipeline.build_from_revision(revision)
        except Exception:
            self._fail_attempt(actor_id, patient_id, attempt_id, trace_id, "snapshot_unavailable")
            raise SnapshotError("snapshot_unavailable", trace_id=trace_id) from None
        try:
            with self.repository.transaction(actor_id=actor_id, patient_id=patient_id) as repo:
                current, refresh_error = self._refresh(repo, actor_id=actor_id, patient_id=patient_id,
                                                       session_id=session_id, trace_id=trace_id)
                if refresh_error or self._identity(current) != identity:
                    error = SnapshotError("session_superseded", trace_id=trace_id)
                    self._finish_failed(repo, actor_id, patient_id, attempt_id, trace_id, "session_superseded")
                else:
                    row = repo.publish(product, identity, self.versions, actor_id=actor_id,
                                       attempt_id=attempt_id, trace_id=trace_id, now=self.clock())
                    result = EnsureSnapshotResult(UUID(row.id), True, repo.full_dto(row))
        except Exception as exc:
            self._fail_attempt(actor_id, patient_id, attempt_id, trace_id, "publication_failed")
            if isinstance(exc, SnapshotError) and exc.code in {"forbidden", "patient_not_found"}:
                raise
            raise SnapshotError("publication_failed", trace_id=trace_id) from None
        if error is not None:
            raise error
        return result

    def _finish_failed(self, repo, actor_id, patient_id, attempt_id, trace_id, code):
        attempt = repo.session.get(SnapshotBuildAttempt, attempt_id)
        if attempt is None or attempt.trace_id != trace_id or attempt.state != "running":
            raise SnapshotError("internal_invariant_failed")
        attempt.state, attempt.finished_at, attempt.error_code = "failed", utc_naive(self.clock()), code
        attempt.error_message = "Snapshot analysis could not complete." if code == "snapshot_unavailable" else "Snapshot publication could not complete."
        write_audit(repo.session, actor_id=actor_id, patient_id=patient_id, trace_id=trace_id,
                    action="snapshot.build", result=code, now=self.clock(), details={"attempt_id": attempt_id})

    def _fail_attempt(self, actor_id, patient_id, attempt_id, trace_id, code):
        # The already authorized attempt may finish after ownership changed. Only its
        # original trace can mark it failed; this internal path returns no patient data.
        with self.repository.transaction(actor_id=actor_id, patient_id=patient_id, authorize=False) as repo:
            self._finish_failed(repo, actor_id, patient_id, attempt_id, trace_id, code)

    @_safe_boundary
    def get_snapshot(self, *, actor_id: int, patient_id: int, snapshot_id: UUID,
                     include_superseded: bool = False) -> SnapshotReadResult:
        if type(include_superseded) is not bool:
            raise SnapshotError("invalid_request")
        return SnapshotReadResult(self._read(actor_id, patient_id, snapshot_id,
                                             projection=False, include_superseded=include_superseded))

    @_safe_boundary
    def get_projection(self, *, actor_id: int, patient_id: int, snapshot_id: UUID) -> ProjectionReadResult:
        return ProjectionReadResult(self._read(actor_id, patient_id, snapshot_id, projection=True))

    @_safe_boundary
    def get_status(self, *, actor_id: int, patient_id: int, snapshot_id: UUID) -> SnapshotStatusResult:
        _scope(actor_id, patient_id)
        snapshot_id = _uuid(snapshot_id)
        trace_id = str(uuid4())
        with self.repository.transaction(actor_id=actor_id, patient_id=patient_id) as repo:
            row = repo.snapshot(snapshot_id, patient_id)
            revision = repo.session.get(GaitSessionRevision, row.session_revision_id)
            self._refresh(repo, actor_id=actor_id, patient_id=patient_id,
                          session_id=revision.session_key, trace_id=trace_id)
            status = repo.status_dto(row)
            write_audit(repo.session, actor_id=actor_id, patient_id=patient_id, snapshot_id=row.id,
                        trace_id=trace_id, action="snapshot.status_read", result="ok", now=self.clock())
        return SnapshotStatusResult(status)

    def _read(self, actor_id, patient_id, snapshot_id, *, projection, include_superseded=False):
        _scope(actor_id, patient_id)
        snapshot_id = _uuid(snapshot_id)
        trace_id, error, payload = str(uuid4()), None, None
        with self.repository.transaction(actor_id=actor_id, patient_id=patient_id) as repo:
            row = repo.snapshot(snapshot_id, patient_id)
            revision = repo.session.get(GaitSessionRevision, row.session_revision_id)
            self._refresh(repo, actor_id=actor_id, patient_id=patient_id, session_id=revision.session_key, trace_id=trace_id)
            if row.state != "published" and not include_superseded:
                error = SnapshotError("snapshot_superseded", trace_id=trace_id)
            else:
                payload = repo.projection_dto(row, self.versions.projection_schema_version) if projection else repo.full_dto(row)
            write_audit(repo.session, actor_id=actor_id, patient_id=patient_id, snapshot_id=row.id,
                        trace_id=trace_id, action="snapshot.projection_read" if projection else "snapshot.read",
                        result=error.code if error else "ok", now=self.clock())
        if error:
            raise error
        return payload

    @_safe_boundary
    def claim_publication(self, request: PublicationClaimRequest) -> PublicationClaimResult:
        _scope(request.actor_id, request.patient_id)
        _uuid(request.snapshot_id)
        trace_id, error, result = str(uuid4()), None, None
        if (type(request.snapshot_state_version) is not int or request.snapshot_state_version < 1
                or not isinstance(request.candidate_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", request.candidate_hash)):
            raise SnapshotError("invalid_request", trace_id=trace_id)
        workflow_run_id = _uuid(request.workflow_run_id)
        with self.repository.transaction(actor_id=request.actor_id, patient_id=request.patient_id) as repo:
            row = repo.snapshot(request.snapshot_id, request.patient_id)
            revision = repo.session.get(GaitSessionRevision, row.session_revision_id)
            self._refresh(repo, actor_id=request.actor_id, patient_id=request.patient_id,
                          session_id=revision.session_key, trace_id=trace_id)
            if row.state != "published" or row.state_version != request.snapshot_state_version:
                error = SnapshotError("stale_snapshot", trace_id=trace_id)
            else:
                existing = repo.session.query(SnapshotPublicationClaim).filter_by(
                    snapshot_id=row.id, workflow_run_id=workflow_run_id).first()
                if existing is not None and (
                    existing.actor_id != request.actor_id or existing.candidate_hash != request.candidate_hash
                    or existing.state_version != request.snapshot_state_version
                ):
                    error = SnapshotError("claim_conflict", trace_id=trace_id)
                else:
                    claim = existing or SnapshotPublicationClaim(
                        id=str(uuid4()), snapshot_id=row.id, state_version=request.snapshot_state_version,
                        workflow_run_id=workflow_run_id, candidate_hash=request.candidate_hash,
                        actor_id=request.actor_id, claimed_at=utc_naive(self.clock()),
                    )
                    if existing is None:
                        repo.session.add(claim)
                        repo.session.flush()
                    payload = dict(claim_id=claim.id, snapshot_id=claim.snapshot_id,
                                   snapshot_state_version=claim.state_version, workflow_run_id=claim.workflow_run_id,
                                   candidate_hash=claim.candidate_hash, actor_id=claim.actor_id,
                                   claimed_at=utc_text(claim.claimed_at))
                    _validator("SnapshotPublicationClaimV1").validate(payload)
                    result = PublicationClaimResult(payload, existing is None)
            write_audit(repo.session, actor_id=request.actor_id, patient_id=request.patient_id,
                        snapshot_id=row.id, trace_id=trace_id, action="snapshot.claim", now=self.clock(),
                        result=error.code if error else ("ok" if result.created else "reused"),
                        details={"workflow_run_id": workflow_run_id})
        if error:
            raise error
        return result
