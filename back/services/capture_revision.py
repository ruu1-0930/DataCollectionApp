"""Freeze a registered capture's explicitly paired raw rows under its collection lock."""
from dataclasses import asdict, dataclass
import json
from uuid import uuid4

from sqlalchemy import or_

from access import AccessError, load_account_context, require_patient_scope
from models.models import CollectionInsoleFrame, CollectionSession, DeviceRawData, GaitSessionRevision, Patient
from services.canonical_json import canonical_json_bytes
from services.collection_ingest import time_string
from services.collection_verification import verification_for_capture
from services.gait_session_revision import SessionResolutionError, raw_rows_fingerprint


@dataclass(frozen=True)
class CaptureClosureEvidence:
    policy_version: str
    reason: str
    stop_received_at: str
    final_counts: dict
    registration_hash: str


@dataclass(frozen=True)
class CaptureRevisionResult:
    revision: GaitSessionRevision
    raw_data_fingerprint: str
    closure_evidence: CaptureClosureEvidence


class CaptureRevisionService:
    def __init__(self, session):
        self.session = session

    def resolve_closed_revision(self, actor, patient_id, capture_id):
        session = self.session
        cap = session.query(CollectionSession).filter_by(
            patient_id=patient_id, capture_id=capture_id).with_for_update().one_or_none()
        if cap is None:
            raise SessionResolutionError('session_not_found')
        account = load_account_context(actor, session=session)
        try:
            for owner in (session.get(Patient, patient_id).clinician_id, cap.clinician_id):
                require_patient_scope(account, owner_id=owner, capability='snapshot.execute')
        except AccessError:
            raise SessionResolutionError('forbidden') from None
        if cap.metadata_schema_version != 1:
            raise SessionResolutionError('snapshot_unavailable')
        if cap.server_stopped_at is None:
            raise SessionResolutionError('collection_in_progress')
        verification = verification_for_capture(session, cap)
        if verification['upload_state'] != 'verified':
            raise SessionResolutionError('snapshot_unavailable')

        links = session.query(CollectionInsoleFrame.left_raw_id, CollectionInsoleFrame.right_raw_id).filter_by(
            capture_id=capture_id).order_by(CollectionInsoleFrame.id).all()
        if not links:
            raise SessionResolutionError('snapshot_unavailable')
        rows = session.query(DeviceRawData).join(CollectionInsoleFrame, or_(
            CollectionInsoleFrame.left_raw_id == DeviceRawData.id,
            CollectionInsoleFrame.right_raw_id == DeviceRawData.id)).filter(
                CollectionInsoleFrame.capture_id == capture_id, DeviceRawData.patient_id == patient_id,
                DeviceRawData.device_id == cap.device_id).order_by(DeviceRawData.collected_at, DeviceRawData.id).all()
        by_id = {row.id: row for row in rows}
        if len(rows) != 2 * len(links) or any(
            left not in by_id or right not in by_id or by_id[left].foot != 'L' or by_id[right].foot != 'R'
            or by_id[left].collected_at is None or by_id[left].collected_at != by_id[right].collected_at
            for left, right in links
        ):
            raise SessionResolutionError('scope_mismatch')
        key = 'C:' + capture_id
        fingerprint = raw_rows_fingerprint(patient_id=patient_id, device_id=cap.device_id, session_id=key, rows=rows)
        evidence = CaptureClosureEvidence('capture-v1', 'capture_stop_receipt', time_string(cap.server_stopped_at),
                                          verification['expected_counts'], cap.registration_hash)
        manifest = canonical_json_bytes({
            'closure': asdict(evidence), 'raw_data_fingerprint': fingerprint,
            'source': {'kind': 'capture', 'capture_id': capture_id, 'test_type': cap.test_type,
                       'registration_hash': cap.registration_hash},
            'frame_pairs': [[left, right] for left, right in links],
        }).decode()
        latest = session.query(GaitSessionRevision).filter_by(patient_id=patient_id, session_key=key).order_by(
            GaitSessionRevision.revision.desc()).first()
        if latest and latest.state == 'closed_by_capture_stop' and latest.closure_evidence_canonical == manifest:
            return CaptureRevisionResult(latest, fingerprint, evidence)
        revision = GaitSessionRevision(
            id=str(uuid4()), patient_id=patient_id, device_id=cap.device_id, session_key=key,
            revision=latest.revision + 1 if latest else 1, state='closed_by_capture_stop',
            ordered_row_ids_canonical=canonical_json_bytes([r.id for r in rows]).decode(),
            first_row_id=rows[0].id, last_row_id=rows[-1].id, row_count=len(rows),
            last_accepted_row_id=max(rows, key=lambda r: (r.uploaded_at, r.id)).id,
            event_start_at=rows[0].collected_at, event_end_at=rows[-1].collected_at,
            ingest_start_at=min(r.uploaded_at for r in rows), ingest_end_at=max(r.uploaded_at for r in rows),
            closure_policy_version=evidence.policy_version, closure_evidence_canonical=manifest,
            closed_at=cap.server_stopped_at)
        session.add(revision)
        session.flush()
        if latest and latest.state == 'closed_by_capture_stop':
            latest.state, latest.superseded_by_revision_id = 'superseded', revision.id
        return CaptureRevisionResult(revision, fingerprint, evidence)


def capture_frames(rows, pairs):
    """Retain firmware frame membership even after per-side numeric exclusions."""
    by_id = {row['id']: row for row in rows}
    frames = []
    for left, right in pairs:
        sides = {'L': by_id.get(left), 'R': by_id.get(right)}
        side = sides['L'] or sides['R']
        if side is not None:
            frames.append({'collected_at': side['collected_at'], **sides})
    return sorted(frames, key=lambda frame: frame['collected_at'])
