"""Materialize immutable revisions from the legacy patient-session stream."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
import json
import math
import re
from collections.abc import Mapping, Sequence
from uuid import uuid4

from config import db
from models.models import DeviceRawData, GaitSessionRevision
from services.canonical_json import canonical_json_bytes, sha256_hex


_SESSION_GAP_SECONDS = 30
_SESSION_POLICY_VERSION = "gap-v1"
_SESSION_BOUND_CHUNK_MINUTES = 5
_SESSION_BOUND_MAX_CHUNKS = 288
_SESSION_ID_PATTERN = re.compile(r"^P(?P<patient_id>\d+)-(?P<timestamp>\d{8}T\d{12})$")
_RAW_VALUE_COLUMNS = tuple(
    [f"p{index}" for index in range(1, 10)]
    + [
        "ax", "ay", "az", "gx", "gy", "gz", "step_length", "walking_speed",
        "single_support_time", "double_support_time",
    ]
)


class SessionResolutionError(ValueError):
    """A safe domain error code for the later snapshot ensure endpoint."""


@dataclass(frozen=True)
class SessionClosureEvidence:
    policy_version: str
    observed_at: datetime
    last_accepted_at: datetime
    idle_seconds: Decimal
    reason: str
    next_accepted_row_id: int | None = None


@dataclass(frozen=True)
class GaitSessionRevisionResult:
    revision: GaitSessionRevision
    raw_data_fingerprint: str
    closure_evidence: SessionClosureEvidence


def _session_id(patient_id: int, start: datetime) -> str:
    return f"P{patient_id}-{start:%Y%m%dT%H%M%S}{start.microsecond:06d}"


def parse_session_start(patient_id: int, session_id: str):
    """Validate the legacy public identifier before any source-row access."""
    match = _SESSION_ID_PATTERN.fullmatch(session_id)
    if match is None or match.group("patient_id") != str(patient_id):
        return None
    try:
        start = datetime.strptime(match.group("timestamp"), "%Y%m%dT%H%M%S%f")
    except (TypeError, ValueError, OverflowError):
        return None
    return start if _session_id(patient_id, start) == session_id else None


def _raw_numeric_for_fingerprint(value) -> Decimal | dict[str, str]:
    """Encode source numerics losslessly, including explicit non-finite markers.

    The tags are fingerprint-only source evidence.  They are never valid DTO
    numbers and are removed by the snapshot pipeline before analysis output.
    """
    if value is None:
        return {"missing_numeric": "true"}
    if isinstance(value, bool):
        raise ValueError("boolean is not a raw numeric value")
    if isinstance(value, float):
        if math.isnan(value):
            return {"invalid_numeric": "nan"}
        if math.isinf(value):
            return {"invalid_numeric": "positive_infinity" if value > 0 else "negative_infinity"}
        return Decimal.from_float(value)
    if isinstance(value, Decimal):
        if value.is_nan():
            return {"invalid_numeric": "nan"}
        if value.is_infinite():
            return {"invalid_numeric": "positive_infinity" if value > 0 else "negative_infinity"}
        return value
    if isinstance(value, int):
        return Decimal(value)
    raise ValueError("raw numeric value has unsupported type")


def _source_timestamp(value: datetime) -> str:
    # Raw source timestamps are legacy naive server-ingestion columns.  Do not falsely
    # label them UTC or coerce them to the millisecond DTO representation here.
    return value.isoformat(timespec="microseconds")


def _row_value(row, field):
    return row[field] if isinstance(row, Mapping) else getattr(row, field)


def raw_rows_fingerprint(*, patient_id: int, device_id: int, session_id: str,
                         rows: Sequence[Mapping[str, object] | DeviceRawData]) -> str:
    """Hash ordered pre-filter source rows with the T02 canonical representation."""
    def fingerprint_row(row):
        return {
            "id": _row_value(row, "id"),
            "foot": _row_value(row, "foot"),
            "collected_at": _source_timestamp(_row_value(row, "collected_at")),
            "uploaded_at": _source_timestamp(_row_value(row, "uploaded_at")),
            "values": {
                column: _raw_numeric_for_fingerprint(_row_value(row, column))
                for column in _RAW_VALUE_COLUMNS
            },
        }

    return sha256_hex(canonical_json_bytes({
        "patient_id": patient_id,
        "device_id": device_id,
        "session_id": session_id,
        "rows": [fingerprint_row(row) for row in rows],
    }))


def _idle_seconds(observed_at: datetime, last_accepted_at: datetime) -> Decimal:
    delta = observed_at - last_accepted_at
    return (
        Decimal(delta.days * 86400 + delta.seconds)
        + Decimal(delta.microseconds) / Decimal(1_000_000)
    )


class GaitSessionRevisionService:
    """Resolve a closed, single-device revision without changing the upload protocol."""

    def __init__(self, *, policy_version=_SESSION_POLICY_VERSION, gap_seconds=_SESSION_GAP_SECONDS):
        self.policy_version = policy_version
        self.gap_seconds = gap_seconds
        self._gap = timedelta(seconds=gap_seconds)

    def resolve_closed_revision(self, *, patient_id: int, session_id: str, now: datetime) -> GaitSessionRevisionResult:
        start = parse_session_start(patient_id, session_id)
        if start is None:
            raise SessionResolutionError("invalid_session_id")

        source_rows, device_id, end, next_row = self._resolve_source_scope(patient_id, start)
        fingerprint = raw_rows_fingerprint(
            patient_id=patient_id,
            device_id=device_id,
            session_id=session_id,
            rows=source_rows,
        )
        latest = (
            GaitSessionRevision.query.filter_by(patient_id=patient_id, session_key=session_id)
            .order_by(GaitSessionRevision.revision.desc())
            .first()
        )
        if latest is not None and latest.device_id != device_id:
            raise SessionResolutionError("scope_mismatch")
        if latest is not None and latest.state == "closed_by_inactivity":
            latest_fingerprint = self._fingerprint_for_revision(latest)
            if latest_fingerprint == fingerprint:
                return GaitSessionRevisionResult(
                    latest, fingerprint, self._stored_closure_evidence(latest)
                )

        evidence = self._closure_evidence(
            device_id=device_id,
            source_rows=source_rows,
            next_accepted_row_id=next_row,
            now=now,
        )
        row_ids = [row.id for row in source_rows]
        evidence_canonical = canonical_json_bytes({
            "policy_version": evidence.policy_version,
            "observed_at": _source_timestamp(evidence.observed_at),
            "last_accepted_at": _source_timestamp(evidence.last_accepted_at),
            "idle_seconds": evidence.idle_seconds,
            "reason": evidence.reason,
            "next_accepted_row_id": evidence.next_accepted_row_id,
        }).decode("utf-8")

        revision_number = 1 if latest is None else latest.revision + 1
        revision = GaitSessionRevision(
            id=str(uuid4()),
            patient_id=patient_id,
            device_id=device_id,
            session_key=session_id,
            revision=revision_number,
            state="closed_by_inactivity",
            ordered_row_ids_canonical=canonical_json_bytes(row_ids).decode("utf-8"),
            first_row_id=row_ids[0],
            last_row_id=row_ids[-1],
            row_count=len(row_ids),
            last_accepted_row_id=max(source_rows, key=lambda row: (row.uploaded_at, row.id)).id,
            event_start_at=start,
            event_end_at=end,
            ingest_start_at=min(row.uploaded_at for row in source_rows),
            ingest_end_at=max(row.uploaded_at for row in source_rows),
            closure_policy_version=self.policy_version,
            closure_evidence_canonical=evidence_canonical,
            closed_at=now,
        )
        db.session.add(revision)
        db.session.flush()
        if latest is not None and latest.state == "closed_by_inactivity":
            latest.state = "superseded"
            latest.superseded_by_revision_id = revision.id
            db.session.flush()
        return GaitSessionRevisionResult(revision, fingerprint, evidence)

    def _resolve_source_scope(self, patient_id, start):
        prior = (
            db.session.query(DeviceRawData.collected_at).filter(
                DeviceRawData.patient_id == patient_id,
                DeviceRawData.collected_at < start,
            )
            .order_by(DeviceRawData.collected_at.desc(), DeviceRawData.id.desc())
            .first()
        )
        if prior is not None and start - prior[0] <= self._gap:
            raise SessionResolutionError("session_not_found")

        anchor_rows = (
            db.session.query(DeviceRawData.device_id)
            .filter_by(patient_id=patient_id, collected_at=start)
            .order_by(DeviceRawData.id.asc())
            .all()
        )
        if not anchor_rows:
            raise SessionResolutionError("session_not_found")
        device_ids = {row[0] for row in anchor_rows}
        if len(device_ids) != 1:
            raise SessionResolutionError("scope_mismatch")
        device_id = next(iter(device_ids))

        end = start
        next_row_id = None
        cursor = start
        previous = None
        for _ in range(_SESSION_BOUND_MAX_CHUNKS):
            upper = cursor + timedelta(minutes=_SESSION_BOUND_CHUNK_MINUTES)
            candidates = (
                db.session.query(
                    DeviceRawData.id, DeviceRawData.collected_at, DeviceRawData.device_id
                )
                .filter(
                    DeviceRawData.patient_id == patient_id,
                    DeviceRawData.collected_at >= cursor,
                    DeviceRawData.collected_at <= upper,
                )
                .order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
                .all()
            )
            for row_id, collected_at, _candidate_device_id in candidates:
                if previous is not None and collected_at <= previous:
                    continue
                if previous is None and collected_at != start:
                    raise SessionResolutionError("session_not_found")
                if previous is not None and collected_at - previous > self._gap:
                    next_row_id = row_id
                    break
                previous = collected_at
                end = collected_at
            if next_row_id is not None:
                break
            if previous is None:
                raise SessionResolutionError("session_not_found")
            if upper - previous >= self._gap:
                break
            cursor = upper
        else:
            raise SessionResolutionError("session_not_found")

        range_devices = (
            db.session.query(DeviceRawData.device_id)
            .filter(
                DeviceRawData.patient_id == patient_id,
                DeviceRawData.collected_at >= start,
                DeviceRawData.collected_at <= end,
            )
            .distinct()
            .all()
        )
        if {row[0] for row in range_devices} != {device_id}:
            raise SessionResolutionError("scope_mismatch")
        scoped_rows = (
            DeviceRawData.query.filter(
                DeviceRawData.patient_id == patient_id,
                DeviceRawData.device_id == device_id,
                DeviceRawData.collected_at >= start,
                DeviceRawData.collected_at <= end,
            )
            .order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
            .all()
        )
        return scoped_rows, device_id, end, next_row_id

    def _closure_evidence(self, *, device_id, source_rows, next_accepted_row_id, now):
        last_accepted_at = max(row.uploaded_at for row in source_rows)
        if next_accepted_row_id is not None:
            return SessionClosureEvidence(
                policy_version=self.policy_version,
                observed_at=now,
                last_accepted_at=last_accepted_at,
                idle_seconds=_idle_seconds(now, last_accepted_at),
                reason="later_accepted_row_gap",
                next_accepted_row_id=next_accepted_row_id,
            )
        latest_device_acceptance = (
            db.session.query(DeviceRawData.uploaded_at)
            .filter(DeviceRawData.device_id == device_id)
            .order_by(DeviceRawData.uploaded_at.desc(), DeviceRawData.id.desc())
            .first()
        )
        trusted_last_accepted_at = latest_device_acceptance[0] if latest_device_acceptance else last_accepted_at
        idle = _idle_seconds(now, trusted_last_accepted_at)
        if idle < Decimal(self.gap_seconds):
            raise SessionResolutionError("collection_in_progress")
        return SessionClosureEvidence(
            policy_version=self.policy_version,
            observed_at=now,
            last_accepted_at=trusted_last_accepted_at,
            idle_seconds=idle,
            reason="device_quiet_period",
        )

    def _fingerprint_for_revision(self, revision):
        rows = (
            DeviceRawData.query.filter(
                DeviceRawData.patient_id == revision.patient_id,
                DeviceRawData.device_id == revision.device_id,
                DeviceRawData.id.in_(self._row_ids(revision)),
            )
            .order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
            .all()
        )
        return raw_rows_fingerprint(
            patient_id=revision.patient_id,
            device_id=revision.device_id,
            session_id=revision.session_key,
            rows=rows,
        )

    @staticmethod
    def _row_ids(revision):
        # The column was written using canonical JSON above; it contains only source IDs.
        return json.loads(revision.ordered_row_ids_canonical)

    @staticmethod
    def _stored_closure_evidence(revision):
        payload = json.loads(revision.closure_evidence_canonical)
        return SessionClosureEvidence(
            policy_version=payload["policy_version"],
            observed_at=datetime.fromisoformat(payload["observed_at"]),
            last_accepted_at=datetime.fromisoformat(payload["last_accepted_at"]),
            idle_seconds=Decimal(payload["idle_seconds"]),
            reason=payload["reason"],
            next_accepted_row_id=payload["next_accepted_row_id"],
        )
