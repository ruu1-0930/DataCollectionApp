"""Short-lived export inventories. B owns every scope decision and capture fence."""
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets

from jsonschema import Draft202012Validator
from sqlalchemy import func
from sqlalchemy.dialects import mysql
from access import AccessError, load_account_context, require_patient_scope
from config import db
from models.models import (Patient, PatientPII, Clinician, CollectionSession, CollectionGpsRaw,
    CollectionRadarRaw, CollectionRadarTarget, AnalysisSnapshot, GaitSessionRevision,
    SnapshotPublicationClaim)
from services.collection_ingest import write_transaction, identifier
from services.collection_records import (_source, _LegacySource, _legacy_sources, _record_metadata,
    _capture_cutoff, _capture_frame_rows, _legacy_frame_rows, _legacy_after, _id_after,
    _encode_cursor, _decode_cursor, _when)
from services.collection_verification import verification_for_capture
from services.data_management_scope import assert_clinical_scope

PAGE = 4 * 1024 * 1024
KINDS = {'profiles': {'patients','collections'}, 'raw': {'frames','gps','radar','targets'},
         'analysis': {'snapshots'}, 'agent': set()}


class ExportInventory(db.Model):
    __tablename__ = 'data_export_inventory'
    id = db.Column(db.String(36), primary_key=True)
    actor_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    request_json = db.Column(db.Text, nullable=False)
    inventory_json = db.Column(db.Text().with_variant(mysql.MEDIUMTEXT(), 'mysql'), nullable=False)
    scope_hash = db.Column(db.String(64), nullable=False)
    state = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    lease_until = db.Column(db.DateTime, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


class ExportGrant(db.Model):
    __tablename__ = 'data_export_grant'
    token_hash = db.Column(db.String(64), primary_key=True)
    export_id = db.Column(db.String(36), db.ForeignKey('data_export_inventory.id', ondelete='CASCADE'), nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)


@lru_cache(maxsize=1)
def _request_schema():
    path = Path(__file__).resolve().parents[1] / 'contracts/data_export_v1.schema.json'
    return Draft202012Validator(json.loads(path.read_text(encoding='utf8'))['contracts']['BundleRequestV1'])


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def _row(model):
    if model is None:
        return None
    result = {}
    for col in model.__table__.columns:
        v = getattr(model, col.key)
        if isinstance(v, datetime):
            v = v.isoformat(timespec='microseconds')
        elif isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, bytes):
            v = v.decode('utf8')
        result[col.key] = v
    return result


def _patient(session, actor_id, patient_id):
    actor = load_account_context(actor_id, session=session)
    patient = session.query(Patient).filter_by(id=patient_id).with_for_update().one_or_none()
    if patient is None:
        raise AccessError(404, 'patient_not_found')
    require_patient_scope(actor, owner_id=patient.clinician_id, capability='data.manage')
    assert_clinical_scope(session, patient_id)
    return patient, None if actor.role == 'admin' else actor.clinician_id


def _profile(session, patient):
    owner = session.get(Clinician, patient.clinician_id)
    pii = _row(session.get(PatientPII, patient.id)) or {}
    return {**_row(patient), **pii, 'doctor_name': owner.name, 'hospital': owner.hospital, 'department': owner.dept}


def _collection(session, source, patient_id):
    if isinstance(source, _LegacySource):
        return source.record(patient_id)
    check = verification_for_capture(session, source)
    item = _record_metadata(source, check, _capture_cutoff(session, source.capture_id, check['received_counts']), None)
    return {**item, 'registration': _row(source), 'expected_counts': check['expected_counts']}


def _inspect(session, patient, owner_id, req):
    raw_scope = req['record_ids']
    if req['scope'] == 'patient':
        captures = session.query(CollectionSession.capture_id).filter_by(patient_id=patient.id)
        if owner_id is not None:
            captures = captures.filter_by(clinician_id=owner_id)
        raw_scope = [r[0] for r in captures]
        raw_scope.extend(s.record_id for s in _legacy_sources(session, patient.id, owner_id))
    records, snaps, claims = {}, [], []
    # A single inventory must fit the control-plane page budget. Never drop records.
    for key in sorted(raw_scope):
        source = _source(session, patient.id, owner_id, key)
        item = _collection(session, source, patient.id)
        if req['mode'] == 'backup' and (item['capture_state'] == 'active' or item['upload_state'] in ('pending','mismatch')):
            raise AccessError(409, 'collection_not_final')
        records[key] = {k:item[k] for k in ('record_version','recorded_through_at','upload_state','test_type','received_counts')}
        records[key]['metadata_hash'] = digest(item)
        if len(records) % 500 == 0 and len(encoded(records)) > PAGE:
            raise AccessError(413, 'inventory_too_large')
    sessions = [('C:' + k if not k.startswith('P') else k) for k in records]
    if 'analysis' in req['contents'] or 'agent' in req['contents']:
        query = session.query(AnalysisSnapshot.id, AnalysisSnapshot.state_version, AnalysisSnapshot.content_hash,
            GaitSessionRevision.session_key, GaitSessionRevision.ordered_row_ids_canonical).join(GaitSessionRevision,
            GaitSessionRevision.id == AnalysisSnapshot.session_revision_id).filter(AnalysisSnapshot.patient_id == patient.id)
        for sid, version, hash_value, session_key, row_ids in query.order_by(AnalysisSnapshot.id).yield_per(100):
            if session_key not in sessions and req['scope'] != 'patient':
                continue
            if session_key.startswith('P') and req['scope'] != 'patient':
                # Gap-v1 snapshots can span rows later claimed by a different capture.
                # No record export may include that other capture's clinical material.
                from services.collection_slices import raw_has_capture
                from models.models import DeviceRawData
                raw_ids = json.loads(row_ids)
                legacy = _source(session, patient.id, owner_id, session_key)
                for start in range(0, len(raw_ids), 500):
                    chunk = raw_ids[start:start+500]
                    q = session.query(DeviceRawData.id).filter(DeviceRawData.id.in_(chunk),
                        DeviceRawData.patient_id == patient.id, ~raw_has_capture(),
                        DeviceRawData.collected_at.between(legacy.start, legacy.end))
                    if owner_id is not None:
                        q = q.filter(DeviceRawData.clinician_id == owner_id)
                    if q.count() != len(chunk):
                        raise AccessError(409, 'mixed_snapshot_scope')
            snaps.append(dict(id=sid, state_version=version, content_hash=hash_value, session_id=session_key))
            if len(snaps) % 1000 == 0 and len(encoded(snaps)) > PAGE:
                raise AccessError(413, 'inventory_too_large')
        for start in range(0, len(snaps), 500):
            ids = [s['id'] for s in snaps[start:start+500]]
            claims.extend(row[0] for row in session.query(SnapshotPublicationClaim.workflow_run_id).filter(
                SnapshotPublicationClaim.snapshot_id.in_(ids)).order_by(SnapshotPublicationClaim.workflow_run_id))
    result = dict(records=records, snapshots=snaps, session_ids=sessions,
        claimed_run_ids=sorted(set(claims)), profile_hash=digest(_profile(session, patient)) if 'profiles' in req['contents'] else None)
    if len(encoded(result)) > PAGE - 16384:
        raise AccessError(413, 'inventory_too_large')
    return result


def _dto(row):
    return dict(schema_version=1, export_id=row.id, scope_hash=row.scope_hash, request=json.loads(row.request_json),
                inventory=json.loads(row.inventory_json), created_at=_when(row.created_at),
                expires_at=_when(row.expires_at), state=row.state)


def create_export_inventory(actor, selection):
    if not _request_schema().is_valid(selection):
        raise AccessError(400, 'invalid_request')
    identifier(selection['request_id'])
    with write_transaction() as session:
        patient, owner = _patient(session, actor.clinician_id, selection['patient_id'])
        now = datetime.utcnow()
        session.query(ExportGrant).filter(ExportGrant.expires_at <= now).delete(synchronize_session=False)
        session.query(ExportInventory).filter(ExportInventory.expires_at <= now).delete(synchronize_session=False)
        existing = session.get(ExportInventory, selection['request_id'])
        if existing:
            if existing.actor_id != actor.clinician_id or json.loads(existing.request_json) != selection:
                raise AccessError(409, 'request_conflict')
            return _dto(existing)
        inventory = _inspect(session, patient, owner, selection)
        row = ExportInventory(id=selection['request_id'], actor_id=actor.clinician_id,
            patient_id=patient.id, request_json=encoded(selection).decode(), inventory_json=encoded(inventory).decode(),
            scope_hash=digest([selection,inventory]), state='building', created_at=now,
            lease_until=now+timedelta(seconds=600), expires_at=now+timedelta(hours=24))
        session.add(row)
        return _dto(row)


def assert_no_export(session, patient_id):
    if session.query(ExportInventory.id).filter(ExportInventory.patient_id == patient_id,
            ExportInventory.state == 'building', ExportInventory.lease_until > datetime.utcnow()).first():
        raise AccessError(409, 'export_in_progress')


def _authorized(session, actor_id, export_id):
    identifier(export_id)
    row = session.get(ExportInventory, export_id)
    if row is None or row.actor_id != actor_id:
        raise AccessError(404, 'export_not_found')
    patient, owner = _patient(session, actor_id, row.patient_id)
    session.refresh(row, with_for_update=True)
    if row.expires_at <= datetime.utcnow():
        raise AccessError(410, 'export_expired')
    return row, patient, owner


def _current(session, row, patient, owner):
    req = json.loads(row.request_json)
    inventory = _inspect(session, patient, owner, req)
    if digest([req,inventory]) != row.scope_hash:
        raise AccessError(409, 'export_scope_changed')
    return inventory


def export_status(actor, export_id, *, validate=False):
    with write_transaction() as session:
        row, patient, owner = _authorized(session, actor.clinician_id, export_id)
        if validate:
            if row.state != 'building' or row.lease_until <= datetime.utcnow():
                raise AccessError(409, 'export_inactive')
            _current(session, row, patient, owner)
        return _dto(row)


def finish_export(actor, export_id, state):
    if state not in ('ready', 'failed'):
        raise AccessError(400, 'invalid_request')
    with write_transaction() as session:
        row, patient, owner = _authorized(session, actor.clinician_id, export_id)
        if row.state != 'building' and row.state != state:
            raise AccessError(409, 'export_inactive')
        if state == 'ready':
            if row.lease_until <= datetime.utcnow():
                raise AccessError(409, 'export_timed_out')
            _current(session, row, patient, owner)
        row.state = state
        return _dto(row)


def _rows(session, kind, patient, owner, inventory, record_id, after):
    if kind == 'patients':
        if not after:
            yield 1, _profile(session, patient)
        return
    if kind == 'snapshots':
        for idx, meta in enumerate(inventory['snapshots'], 1):
            if idx > (after or 0):
                snap = session.get(AnalysisSnapshot, meta['id'])
                data = _row(snap)
                if sha256(data['canonical_payload'].encode()).hexdigest() != meta['content_hash']:
                    raise AccessError(409, 'snapshot_hash_mismatch')
                yield idx, {**data, 'session_id': meta['session_id']}
        return
    if record_id not in inventory['records']:
        raise AccessError(403, 'scope_mismatch')
    source = _source(session, patient.id, owner, record_id)
    if kind == 'collections':
        if not after:
            yield 1, _collection(session, source, patient.id)
    elif kind == 'frames':
        if isinstance(source, _LegacySource):
            for key, left, right in _legacy_frame_rows(session, patient.id, owner, source, _legacy_after(after)):
                yield [key[0].isoformat(timespec='microseconds'),key[1]], dict(frame=None,left=_row(left),right=_row(right))
        else:
            # Bounded keyset batches; include original per-foot IDs and values, never UI projections.
            offset = _id_after(after)
            while True:
                batch = list(_capture_frame_rows(session, source, offset, 100))
                if not batch:
                    break
                for frame, left, right in batch:
                    if left is None or right is None:
                        raise AccessError(409, 'raw_link_missing')
                    yield frame.id, dict(frame=_row(frame),left=_row(left),right=_row(right))
                offset = batch[-1][0].id
    elif not isinstance(source, _LegacySource):
        model = {'gps':CollectionGpsRaw,'radar':CollectionRadarRaw,'targets':CollectionRadarTarget}[kind]
        q = session.query(model).filter(model.id > _id_after(after))
        if kind == 'targets':
            q = q.join(CollectionRadarRaw, model.parent_id == CollectionRadarRaw.id).filter(CollectionRadarRaw.capture_id == record_id)
        else:
            q = q.filter(model.capture_id == record_id)
        for item in q.order_by(model.id).limit(1001).yield_per(100):
            yield item.id, _row(item)


def read_export_page(actor, export_id, kind, cursor=None, limit=1000, max_bytes=PAGE, *, record_id=None):
    if type(limit) is not int or not 1 <= limit <= 1000 or type(max_bytes) is not int or not 1 <= max_bytes <= PAGE:
        raise AccessError(400, 'invalid_page')
    with write_transaction() as session:
        row, patient, owner = _authorized(session, actor.clinician_id, export_id)
        if row.state != 'building' or row.lease_until <= datetime.utcnow():
            raise AccessError(409, 'export_inactive')
        req = json.loads(row.request_json)
        if not any(kind in KINDS[c] for c in req['contents']):
            raise AccessError(403, 'content_not_selected')
        inv = _current(session,row,patient,owner)
        binding = digest([export_id,row.scope_hash,kind,record_id])
        after = _decode_cursor(cursor, binding)
        items, used, last = [], 0, None
        page = dict(schema_version=1, export_id=export_id, scope_hash=row.scope_hash, kind=kind, record_id=record_id, items=items, next_cursor=None)
        for key, item in _rows(session,kind,patient,owner,inv,record_id,after):
            n = len(encoded(item)) + 1
            if len(items) == limit or used + n + 1024 > max_bytes:
                if not items:
                    raise AccessError(413, 'export_item_too_large')
                page['next_cursor'] = _encode_cursor(binding,last)
                break
            items.append(item)
            last, used = key, used+n
        if len(encoded(page)) > max_bytes:
            raise AccessError(413, 'export_item_too_large')
        return page


def issue_grant(actor, export_id):
    with write_transaction() as session:
        row, patient, owner = _authorized(session, actor.clinician_id, export_id)
        if row.state != 'ready':
            raise AccessError(409, 'export_not_ready')
        _current(session,row,patient,owner)
        grant = secrets.token_urlsafe(32)
        expires = min(row.expires_at, datetime.utcnow()+timedelta(seconds=300))
        session.add(ExportGrant(export_id=export_id, token_hash=sha256(grant.encode()).hexdigest(), expires_at=expires))
        return dict(schema_version=1, bundle_id=export_id, grant=grant, expires_at=_when(expires))


def redeem_grant(export_id, token):
    if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
        raise AccessError(403,'invalid_download_grant')
    with write_transaction() as session:
        grant = session.get(ExportGrant, sha256(token.encode()).hexdigest())
        row = session.get(ExportInventory,export_id)
        if not row or not grant or grant.export_id != export_id or grant.expires_at <= datetime.utcnow():
            raise AccessError(403,'invalid_download_grant')
        row, patient, owner = _authorized(session,row.actor_id,export_id)
        if row.state != 'ready':
            raise AccessError(409,'export_not_ready')
        _current(session,row,patient,owner)
        return dict(schema_version=1,bundle_id=row.id,scope_hash=row.scope_hash,patient_id=row.patient_id)

