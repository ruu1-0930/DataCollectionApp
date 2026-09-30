"""Allowlisted, append-only operational audit in the caller's source transaction."""

from datetime import timedelta, timezone
import re
from uuid import uuid4

from models.models import ClinicalAuditEvent
from services.canonical_json import canonical_json_bytes, sha256_hex

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
