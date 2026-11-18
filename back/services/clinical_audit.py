"""Allowlisted, append-only operational audit in the caller's source transaction."""

from datetime import timedelta, timezone
import re
from uuid import uuid4

from models.models import ClinicalAuditEvent
from services.canonical_json import canonical_json_bytes, sha256_hex


def verify_patient_audit(session, patient_id):
    """Validate surviving bytes and follow minimal deletion bridges across removed events."""
    from services.data_management_scope import ManagementAuditBridge, ManagementOperation
    events = session.query(ClinicalAuditEvent).filter_by(patient_id=patient_id).all()
    known = {row.event_hash: row.previous_event_hash for row in events}
    for row in events:
        if sha256_hex(row.canonical_payload.encode()) != row.event_hash:
            raise ValueError('clinical_audit_chain_invalid')
    removed = dict(session.query(ManagementAuditBridge.event_hash, ManagementAuditBridge.previous_event_hash)
        .join(ManagementOperation, ManagementOperation.id == ManagementAuditBridge.operation_id)
        .filter(ManagementOperation.patient_id == patient_id))
    links = dict(removed, **known)
    for event in events:
        visited = set()
        current = event.event_hash
        while current is not None:
            if current in visited or current not in links:
                raise ValueError('clinical_audit_chain_invalid')
            visited.add(current)
            current = links[current]


def _verify_predecessor(session, patient_id, event):
    from services.data_management_scope import ManagementAuditBridge, ManagementOperation
    if event is None:
        return
    if sha256_hex(event.canonical_payload.encode()) != event.event_hash:
        raise ValueError('clinical_audit_chain_invalid')
    current, visited = event.previous_event_hash, set()
    while current is not None:
        if current in visited:
            raise ValueError('clinical_audit_chain_invalid')
        visited.add(current)
        if session.query(ClinicalAuditEvent.id).filter_by(patient_id=patient_id, event_hash=current).first():
            return
        bridge = (session.query(ManagementAuditBridge.previous_event_hash)
            .join(ManagementOperation, ManagementOperation.id == ManagementAuditBridge.operation_id)
            .filter(ManagementOperation.patient_id == patient_id, ManagementAuditBridge.event_hash == current).first())
        if bridge is None:
            raise ValueError('clinical_audit_chain_invalid')
        current = bridge[0]

_ACTIONS = {
    "snapshot.build", "snapshot.publish", "snapshot.read", "snapshot.status_read", "snapshot.projection_read",
    "snapshot.claim", "snapshot.superseded", "session.superseded",
}
_RESULTS = {
    "running", "succeeded", "failed", "ok", "reused", "snapshot_building",
    "snapshot_unavailable", "publication_failed", "snapshot_superseded",
    "session_superseded", "stale_snapshot", "claim_conflict",
}
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


def utc_naive(value):
    """Database metadata is UTC, unlike the legacy raw source clock."""
    if value.tzinfo is None:
        raise ValueError("metadata_clock_must_be_aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_text(value):
    return value.replace(tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_audit(session, *, actor_id, patient_id, trace_id, action, result, now,
                snapshot_id=None, session_revision_id=None, details=None):
    # Arbitrary exception text, clinical evidence and raw values have no channel here.
    details = dict(details or {})
    if action not in _ACTIONS or result not in _RESULTS:
        raise ValueError("unsafe_audit")
    for key, value in details.items():
        if key in {"attempt_id", "workflow_run_id", "replacement_snapshot_id"}:
            valid = isinstance(value, str) and _UUID.fullmatch(value)
        elif key in {"candidate_hash", "identity_fingerprint", "content_hash"}:
            valid = isinstance(value, str) and _HASH.fullmatch(value)
        elif key in {"snapshot_state_version", "attempt_number"}:
            valid = type(value) is int and value >= 1
        else:
            valid = False
        if not valid:
            raise ValueError("unsafe_audit")
    if not _UUID.fullmatch(str(trace_id)):
        raise ValueError("unsafe_audit")
    previous = (session.query(ClinicalAuditEvent).filter_by(patient_id=patient_id)
                .order_by(ClinicalAuditEvent.created_at.desc()).first())
    _verify_predecessor(session, patient_id, previous)
    created = utc_naive(now)
    # DATETIME(3) and canonical RFC3339 both persist milliseconds. The caller's
    # patient lock makes a whole-millisecond advance a durable chain total order.
    created = created.replace(microsecond=created.microsecond // 1000 * 1000)
    if previous is not None and created <= previous.created_at:
        created = previous.created_at.replace(microsecond=previous.created_at.microsecond // 1000 * 1000)
        created += timedelta(milliseconds=1)
    event_id = str(uuid4())
    body = dict(event_id=event_id, trace_id=str(trace_id), actor_id=actor_id,
                patient_id=patient_id, session_revision_id=session_revision_id,
                snapshot_id=snapshot_id, action=action, result=result, details=details,
                previous_event_hash=previous.event_hash if previous else None,
                created_at=utc_text(created))
    canonical = canonical_json_bytes(body)
    row = ClinicalAuditEvent(
        id=event_id, trace_id=str(trace_id), actor_id=actor_id, patient_id=patient_id,
        session_revision_id=session_revision_id, snapshot_id=snapshot_id,
        action=action, result=result, canonical_payload=canonical.decode(),
        event_hash=sha256_hex(canonical), previous_event_hash=body["previous_event_hash"],
        created_at=created,
    )
    session.add(row)
    session.flush()
    return row
