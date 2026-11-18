"""Reconcile a capture's final declaration against persisted raw-event rows."""

import json
from typing import Literal, Optional, TypedDict

from sqlalchemy import case, func

from access import load_account_context, require_capability, require_patient_scope
from models.models import CollectionGpsRaw, CollectionRadarRaw
from services.canonical_json import canonical_json_bytes, sha256_hex
from services.collection_ingest import STREAM_MODELS, identifier, lock_capture_scope, server_now, time_string, write_transaction


class CollectionCounts(TypedDict):
    insole: int
    gps: int
    radar: int


class CollectionVerificationV1(TypedDict):
    record_id: str
    record_version: str
    observed_at: str
    expected_counts: Optional[CollectionCounts]
    received_counts: CollectionCounts
    upload_state: Literal['pending', 'verified', 'mismatch', 'unknown']
    quality_observations: list[str]


def verification_for_capture(session, capture, *, observed_at=None) -> CollectionVerificationV1:
    """Project from the caller's transaction and capture lock."""
    counts = {}
    observations = []
    gps_without_fix = func.count(case((CollectionGpsRaw.fix.is_(False), 1)))
    radar_stale = func.count(case((CollectionRadarRaw.stale.is_(True), 1)))
    flags = {'gps': (gps_without_fix, 'gps_contains_no_fix'), 'radar': (radar_stale, 'radar_contains_stale')}
    for stream, model in STREAM_MODELS.items():
        matching = model.capture_id == capture.capture_id
        if stream in flags:
            metric, observation = flags[stream]
            count, flagged = session.query(func.count(model.id), metric).filter(matching).one()
            if flagged:
                observations.append(observation)
        else:
            count = session.query(func.count(model.id)).filter(matching).scalar()
            if count == 0:
                observations.append('no_insole_frames')
        counts[stream] = count

    expected = json.loads(capture.final_counts_json) if capture.final_counts_json is not None else None
    if capture.metadata_schema_version != 1:
        state = 'unknown'
    elif not capture.mobile_stopped_at or not capture.server_stopped_at or expected is None:
        state = 'pending'
    else:
        state = 'verified' if expected == counts else 'mismatch'

    evidence = {'record_id': capture.capture_id, 'clinician_id': capture.clinician_id,
                'patient_id': capture.patient_id, 'device_id': capture.device_id,
                'registration_hash': capture.registration_hash,
                'mobile_started_at': time_string(capture.mobile_started_at),
                'server_created_at': time_string(capture.server_created_at),
                'mobile_stopped_at': time_string(capture.mobile_stopped_at) if capture.mobile_stopped_at else None,
                'server_stopped_at': time_string(capture.server_stopped_at) if capture.server_stopped_at else None,
                'expected_counts': expected, 'received_counts': counts, 'upload_state': state,
                'quality_observations': observations}
    return {'record_id': capture.capture_id, 'observed_at': time_string(observed_at or server_now()),
            'record_version': sha256_hex(canonical_json_bytes(evidence)), 'expected_counts': expected,
            'received_counts': counts, 'upload_state': state, 'quality_observations': observations}


def verify_capture(actor, capture_id) -> CollectionVerificationV1:
    identifier(capture_id)
    with write_transaction() as session:
        account = load_account_context(actor.clinician_id, session=session)
        require_capability(account, 'clinical.read')
        patient, capture = lock_capture_scope(session, capture_id)
        require_patient_scope(account, owner_id=capture.clinician_id, capability='clinical.read')
        require_patient_scope(account, owner_id=patient.clinician_id, capability='clinical.read', patient_id=patient.id)
        return verification_for_capture(session, capture)
