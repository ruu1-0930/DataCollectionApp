"""Explicit business projections. No refresh, model inference or ORM writes."""

from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from sqlalchemy import String, cast, exists, func, select, text
from sqlalchemy.orm import Session, aliased

from access import require_capability
from config import db
from models.models import (AnalysisSnapshot, Clinician, Device, DeviceRawData,
                           GaitSessionRevision, Patient, PatientPII)
from services.canonical_json import canonical_json_bytes, sha256_hex
from services.clinical_audit import utc_text
from services.gait_session_revision import _session_id, _RAW_VALUE_COLUMNS
from services.snapshot_repository import AnalysisSnapshotRepository


class AdminReadError(RuntimeError):
    def __init__(self, status_code):
        super().__init__('admin_read_failed')
        self.status_code = status_code


@lru_cache(maxsize=None)
def _validator(name):
    root = Path(__file__).resolve().parents[1] / 'contracts'
    admin = json.loads((root / 'admin_business_v1.schema.json').read_text(encoding='utf-8'))
    gait = json.loads((root / 'gait_snapshot_v1.schema.json').read_text(encoding='utf-8'))
    registry = Registry().with_resource(gait['$id'], Resource.from_contents(gait))
    return Draft202012Validator({'$schema': admin['$schema'], '$defs': admin['$defs'],
                                 '$ref': '#/$defs/' + name}, registry=registry)


def validate_result(name, value):
    _validator(name).validate(value)
    json.dumps(value, allow_nan=False)
    return value


def _source_time(value):
    return value.isoformat(timespec='microseconds') if value else None


def _clinician(row):
    return {key: getattr(row, key) for key in ('id', 'hospital', 'dept', 'name', 'phone', 'role')} | {
        'created_at': utc_text(row.created_at) if row.created_at else None}


def _patient(row, owner, pii, *, detail=False):
    value = {key: getattr(row, key) for key in ('id', 'subject_id', 'gender', 'age')}
    value.update(name=pii.name if pii else None, phone=pii.phone if pii else None,
                 created_at=utc_text(row.created_at) if row.created_at else None,
                 last_collected_at=_source_time(row.last_collected_at), owner=_clinician(owner))
    if detail:
        value.update(email=pii.email if pii else None, address=pii.address if pii else None)
    return value


def _page(query, options, serialize):
    page, size = options['page'], options['page_size']
    total = query.order_by(None).count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return dict(items=[serialize(row) for row in rows], total=total, page=page, page_size=size)


def _range(query, column, options):
    if options.get('start') is not None:
        query = query.filter(column >= options['start'])
    if options.get('end') is not None:
        query = query.filter(column < options['end'] if options.get('end_exclusive') else column <= options['end'])
    return query


def _patient_query(session):
    return session.query(Patient, Clinician, PatientPII).join(Clinician).outerjoin(PatientPII)


def _parent(session, patient_id):
    row = _patient_query(session).filter(Patient.id == patient_id).one_or_none()
    if row is None:
        raise AdminReadError(404)
    return row


def _starts(session, patient_id):
    """Gap >30 seconds starts a session; DB pagination, no full-history Python scan.

    SQLite text arithmetic preserves six source decimals (datetime() alone rounds
    fractions). MySQL source columns support native DATE_SUB microseconds.
    """
    current, prior = aliased(DeviceRawData), aliased(DeviceRawData)
    if session.bind.dialect.name == 'mysql':
        cutoff = func.date_sub(current.collected_at, text('INTERVAL 30 SECOND'))
    else:
        stamp = cast(current.collected_at, String)
        cutoff = func.datetime(func.substr(stamp, 1, 19), '-30 seconds').concat(func.substr(stamp, 20, 7))
    preceding = exists(select(prior.id).where(
        prior.patient_id == current.patient_id, prior.collected_at < current.collected_at,
        prior.collected_at >= cutoff)).correlate(current)
    return session.query(current.collected_at.label('start_at')).filter(
        current.patient_id == patient_id, current.collected_at.isnot(None), ~preceding).distinct()


class AdminBusinessService:
    def __init__(self, engine=None):
        self.engine = engine if engine is not None else db.engine

    def read(self, account, action, options, *, patient_id=None, snapshot_id=None):
        require_capability(account, 'admin.read')
        # A separate, autoflush-disabled identity map cannot flush request state.
        # Session.close rolls back its read transaction; no commit or patient lock.
        with Session(self.engine, autoflush=False) as session:
            parent = _parent(session, patient_id) if patient_id is not None else None
            owner_id = parent[0].clinician_id if parent else None
            value = getattr(self, action)(session, options, patient_id, snapshot_id, parent)
            return value, owner_id

    def list_clinicians(self, session, options, *_):
        query = session.query(Clinician)
        for field in ('hospital', 'dept'):
            if field in options:
                query = query.filter(getattr(Clinician, field) == options[field])
        if 'clinician_id' in options:
            query = query.filter(Clinician.id == options['clinician_id'])
        return _page(query.order_by(Clinician.created_at.desc(), Clinician.id.desc()), options, _clinician)

    def list_patients(self, session, options, *_):
        query = _patient_query(session)
        for field, column in [('hospital', Clinician.hospital), ('clinician_id', Patient.clinician_id),
                              ('patient_id', Patient.id), ('subject_id', Patient.subject_id)]:
            if field in options:
                query = query.filter(column == options[field])
        return _page(query.order_by(Patient.created_at.desc(), Patient.id.desc()), options,
                     lambda row: _patient(*row))

    def get_patient(self, session, options, patient_id, snapshot_id, parent):
        return _patient(*parent, detail=True)

    def list_devices(self, session, options, *_):
        query = session.query(Device, Clinician).join(Clinician)
        for field, column in [('hospital', Clinician.hospital), ('clinician_id', Device.clinician_id),
                              ('device_code', Device.device_code)]:
            if field in options:
                query = query.filter(column == options[field])
        def serialize(row):
            device, owner = row
            return {key: getattr(device, key) for key in ('id', 'device_code', 'device_name', 'is_enabled')} | {
                'created_at': utc_text(device.created_at) if device.created_at else None, 'owner': _clinician(owner)}
        return _page(query.order_by(Device.created_at.desc(), Device.id.desc()), options, serialize)

    def list_sessions(self, session, options, patient_id, *_):
        all_starts = _starts(session, patient_id)
        starts = all_starts.subquery()
        query = _range(session.query(starts.c.start_at), starts.c.start_at, options)
        def serialize(row):
            start = row.start_at
            next_start = session.query(func.min(starts.c.start_at)).filter(starts.c.start_at > start).scalar()
            raw = session.query(func.count(DeviceRawData.id), func.max(DeviceRawData.collected_at)).filter(
                DeviceRawData.patient_id == patient_id, DeviceRawData.collected_at >= start)
            if next_start is not None:
                raw = raw.filter(DeviceRawData.collected_at < next_start)
            count, end = raw.one()
            return dict(session_id=_session_id(patient_id, start), patient_id=patient_id,
                        start_at=_source_time(start), end_at=_source_time(end), row_count=count)
        return _page(query.order_by(starts.c.start_at.desc()), options, serialize)

    def list_raw_data(self, session, options, patient_id, *_):
        if 'device_id' in options and not session.query(DeviceRawData.id).filter_by(
                patient_id=patient_id, device_id=options['device_id']).first():
            raise AdminReadError(404)
        query = session.query(DeviceRawData).filter_by(patient_id=patient_id)
        for field in ('foot', 'device_id'):
            if field in options:
                query = query.filter(getattr(DeviceRawData, field) == options[field])
        query = _range(query, DeviceRawData.collected_at, options)
        def serialize(row):
            unavailable = []
            def number(value, key):
                if value is None or not math.isfinite(value):
                    unavailable.append(key)
                    return None
                return value
            value = {key: getattr(row, key) for key in ('id', 'patient_id', 'device_id', 'clinician_id', 'foot')}
            value.update({key: number(getattr(row, key), key) for key in _RAW_VALUE_COLUMNS})
            stored = row.transformed_data
            value.update(collected_at=_source_time(row.collected_at), uploaded_at=_source_time(row.uploaded_at),
                         transformed={key: number(getattr(stored, key), 'transformed.' + key)
                                      for key in ('T1', 'T2', 'T3', 'T4', 'T5')} if stored else None,
                         unavailable_fields=unavailable)
            return value
        return _page(query.order_by(DeviceRawData.collected_at.desc(), DeviceRawData.id.desc()), options, serialize)

    def list_snapshots(self, session, options, patient_id, *_):
        query = session.query(AnalysisSnapshot, GaitSessionRevision.session_key).join(
            GaitSessionRevision, AnalysisSnapshot.session_revision_id == GaitSessionRevision.id).filter(
                AnalysisSnapshot.patient_id == patient_id)
        if not options.get('include_superseded', False):
            query = query.filter(AnalysisSnapshot.state == 'published')
        if 'session_id' in options:
            query = query.filter(GaitSessionRevision.session_key == options['session_id'])
        def serialize(row):
            snapshot, session_id = row
            value = {key: getattr(snapshot, key) for key in ('patient_id', 'session_revision_id', 'state',
                'content_hash', 'raw_data_fingerprint', 'snapshot_schema_version', 'analyzer_set_version',
                'threshold_profile_version')}
            return value | dict(snapshot_id=snapshot.id, session_id=session_id,
                snapshot_state_version=snapshot.state_version, created_at=utc_text(snapshot.created_at),
                superseded_by=snapshot.superseded_by_snapshot_id)
        return _page(query.order_by(AnalysisSnapshot.created_at.desc(), AnalysisSnapshot.id.desc()), options, serialize)

    def get_snapshot(self, session, options, patient_id, snapshot_id, parent):
        row = session.query(AnalysisSnapshot).filter_by(patient_id=patient_id, id=snapshot_id).one_or_none()
        if row is None:
            raise AdminReadError(404)
        try:
            original = json.loads(row.canonical_payload)
            if (not isinstance(original, dict) or original.get('content_hash') != row.content_hash
                    or sha256_hex(canonical_json_bytes({k: v for k, v in original.items() if k != 'content_hash'})) != row.content_hash
                    or canonical_json_bytes(original).decode() != row.canonical_payload):
                raise ValueError('invalid_saved_content')
            payload = AnalysisSnapshotRepository(self.engine, session=session).full_dto(row)
            revision = session.get(GaitSessionRevision, row.session_revision_id)
            if (payload['patient_id'] != patient_id or payload['session_revision_id'] != row.session_revision_id
                    or payload['session_id'] != revision.session_key
                    or payload['session']['raw_data_fingerprint'] != row.raw_data_fingerprint):
                raise ValueError('invalid_saved_identity')
            return dict(snapshot=payload, source_check='not_performed', read_at=utc_text(datetime.now(timezone.utc)))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise AdminReadError(503) from exc
