"""Atomic collection ingestion; mobile clocks never replace legacy raw clocks."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
import math
import json
from pathlib import Path
import re
import unicodedata
from uuid import UUID

from jsonschema import Draft202012Validator, ValidationError
from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import db
from models.models import CollectionSession, CollectionInsoleFrame, CollectionGpsRaw, CollectionRadarRaw, CollectionRadarTarget, Device, Patient, DeviceRawData
from access import load_account_context, require_capability
from services.canonical_json import canonical_json_bytes, sha256_hex


SAFE_INTEGER = 9007199254740991
STREAM_MODELS = {'insole': CollectionInsoleFrame, 'gps': CollectionGpsRaw, 'radar': CollectionRadarRaw}
TIME_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$')
NUMBER_PATTERN = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
LEFT_FIELDS = {**{f'p{i}':f'lp{i}' for i in range(1,10)},
    'ax':'ax','ay':'ay','az':'az','gx':'gx','gy':'gy','gz':'gz',
    'step_length':'left_step_size','walking_speed':'left_speed',
    'single_support_time':'left_single_sp_time','double_support_time':'left_double_sp_time'}
RIGHT_FIELDS = {**{f'p{i}':f'rp{i}' for i in range(1,10)},
    'ax':'right_ax','ay':'right_ay','az':'right_az','gx':'right_gx','gy':'right_gy','gz':'right_gz',
    'step_length':'right_step_size','walking_speed':'right_speed',
    'single_support_time':'right_single_sp_time','double_support_time':'right_double_sp_time'}


class CollectionError(ValueError):
    def __init__(self, status=400):
        self.status = status
        super().__init__('collection request rejected')


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise CollectionError()


def identifier(value):
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise CollectionError() from None
    return value


def integer(value):
    if type(value) is not int or not 0 <= value <= SAFE_INTEGER:
        raise CollectionError()
    return value


def mobile_time(value):
    if not isinstance(value, str) or not TIME_PATTERN.fullmatch(value):
        raise CollectionError()
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')
    except ValueError:
        raise CollectionError() from None


def time_string(value):
    return value.isoformat(timespec='milliseconds') + 'Z'


def server_now():
    value = datetime.now(timezone.utc).replace(tzinfo=None)
    return value.replace(microsecond=value.microsecond // 1000 * 1000)


def gps_payload(payload):
    exact(payload, {'raw_line'})
    line = payload['raw_line']
    if not isinstance(line, str) or len(line) > 1024 or '\n' in line or '\r' in line:
        raise CollectionError()
    parts = line.split(',')
    if len(parts) != 13 or parts[0] != 'GPS1' or parts[2] not in {'0','1'}:
        raise CollectionError()
    values = dict(zip(('seq','fix','lat','lon','alt','speed','sats','hdop','age','utc','chars','errors'), parts[1:]))
    for name in ('seq','sats','age','chars','errors'):
        if re.fullmatch(r'[0-9]+', values[name]) is None:
            raise CollectionError()
        values[name] = integer(int(values[name]))
    values['fix'] = values['fix'] == '1'
    for name in ('lat','lon','alt','speed','hdop'):
        source = values[name]
        # Firmware's lowercase nan is a missing-value marker only without a fix.
        # Preserve raw_line while storing SQL NULL / emitting JSON null.
        if source == '' or (not values['fix'] and source == 'nan'):
            values[name] = None
        elif NUMBER_PATTERN.fullmatch(source) is None:
            raise CollectionError()
        else:
            values[name] = float(source)
            if not math.isfinite(values[name]):
                raise CollectionError()
    values['raw_line'] = line
    return values


def normalized_event(value):
    exact(value, {'event_id','stream','stream_sequence','connection_epoch','mobile_received_at','payload'})
    identifier(value['event_id'])
    integer(value['stream_sequence'])
    integer(value['connection_epoch'])
    received = mobile_time(value['mobile_received_at'])
    if value['stream'] == 'gps':
        parsed = gps_payload(value['payload'])
        canonical_payload = value['payload']
    elif value['stream'] == 'insole':
        exact(value['payload'], set(LEFT_FIELDS.values()) | set(RIGHT_FIELDS.values()))
        parsed = {}
        for key, number in value['payload'].items():
            try:
                finite = type(number) in (int,float) and math.isfinite(number)
            except OverflowError:
                finite = False
            if not finite:
                raise CollectionError()
            parsed[key] = number
        canonical_payload = {key: (Decimal(number) if type(number) is int else Decimal(str(number)).normalize()) if number else Decimal(0)
                             for key,number in parsed.items()}
    elif value['stream'] == 'radar':
        from services.radar_protocol import parse_radar_payload, canonical_radar_payload
        parsed = parse_radar_payload(value['payload'])
        canonical_payload = canonical_radar_payload(parsed)
    else:
        raise CollectionError()
    identity = {key:value[key] for key in ('event_id','stream','stream_sequence','connection_epoch','mobile_received_at')}
    digest = sha256_hex(canonical_json_bytes(dict(identity, payload=canonical_payload)))
    return dict(identity, received=received, parsed=parsed, digest=digest)


@contextmanager
def write_transaction():
    with db.engine.connect() as connection:
        # The account read precedes the capture lock. A repeatable-read view could
        # otherwise hide rows committed while that lock was being acquired.
        if connection.dialect.name == 'mysql':
            connection = connection.execution_options(isolation_level='READ COMMITTED')
        with Session(bind=connection, expire_on_commit=False) as session:
            try:
                if connection.dialect.name == 'sqlite':
                    session.execute(text('BEGIN IMMEDIATE'))
                else:
                    session.begin()
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise


def lock_capture_scope(session, capture_id):
    """Discover the immutable parent, then consistently lock patient before capture."""
    from services.data_management_scope import assert_capture_id_available
    assert_capture_id_available(session, capture_id)
    patient_id = session.query(CollectionSession.patient_id).filter_by(capture_id=capture_id).scalar()
    if patient_id is None:
        assert_capture_id_available(session, capture_id)
        raise CollectionError(404)
    patient = session.query(Patient).filter_by(id=patient_id).populate_existing().with_for_update().one_or_none()
    capture = session.query(CollectionSession).filter_by(
        capture_id=capture_id, patient_id=patient_id).populate_existing().with_for_update().one_or_none()
    from services.data_management_scope import assert_clinical_scope
    assert_capture_id_available(session, capture_id)
    assert_clinical_scope(session, patient_id, capture_id=capture_id)
    if patient is None or capture is None:
        raise CollectionError(404)
    return patient, capture


def _owned_capture(session, capture_id, actor_id):
    identifier(capture_id)
    account = load_account_context(actor_id, session=session)
    require_capability(account, 'clinician.write')
    patient, capture = lock_capture_scope(session, capture_id)
    if capture.clinician_id != actor_id:
        raise CollectionError(403)
    device = session.get(Device, capture.device_id)
    if patient is None or device is None or patient.clinician_id != actor_id or device.clinician_id != actor_id:
        raise CollectionError(403)
    return capture


def _capture_dto(capture):
    return {'capture_id':capture.capture_id}


def _request_version(payload, version):
    declared = payload.get('schema_version', 1) if isinstance(payload, dict) else None
    if type(declared) is not int or declared not in (1, 2) or (version is not None and declared != version):
        raise CollectionError()
    return declared


@lru_cache(maxsize=1)
def _registration_validator():
    path = Path(__file__).resolve().parents[1] / 'contracts' / 'collection_registration_v1.schema.json'
    return Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))


def _registration_fields(value, patient_id):
    try:
        _registration_validator().validate(value)
        snapshot = dict(value['patient_snapshot'])
        if (type(value['schema_version']) is not int or integer(value['patient_id']) != patient_id
                or type(snapshot['age']) is not int or not snapshot['name'].strip()):
            raise CollectionError()
        snapshot['name'] = unicodedata.normalize('NFC', snapshot['name'])
        # JSON numbers stay numbers in the snapshot, with one encoding for integral values.
        for field in ('height_cm', 'weight_kg', 'shoe_size_eu'):
            number = snapshot[field]
            if isinstance(number, float) and number.is_integer():
                snapshot[field] = int(number)
        normalized = dict(value, patient_snapshot=snapshot, remarks=unicodedata.normalize('NFC', value['remarks']))
        _registration_validator().validate(normalized)
        encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
        digest = sha256_hex(encoded.encode('utf-8'))
    except (ValidationError, ValueError, OverflowError):
        raise CollectionError() from None
    return {'metadata_schema_version': 1, 'test_type': value['test_type'],
            'registration_json': encoded, 'registration_hash': digest}


def create_capture(actor_id, payload, *, version=None):
    fields = {'capture_id', 'patient_id', 'device_code', 'mobile_started_at'}
    version = _request_version(payload, version)
    exact(payload, fields | {'schema_version', 'registration'} if version == 2 else fields)
    capture_id = identifier(payload['capture_id'])
    patient_id = integer(payload['patient_id'])
    if patient_id < 1 or not isinstance(payload['device_code'], str) or not payload['device_code']:
        raise CollectionError()
    started = mobile_time(payload['mobile_started_at'])
    registration = _registration_fields(payload['registration'], patient_id) if version == 2 else {}
    def same_request(capture, device):
        return (capture.clinician_id, capture.patient_id, capture.device_id, capture.mobile_started_at,
                capture.metadata_schema_version, capture.registration_hash) == (
                    actor_id, patient_id, device.id, started, registration.get('metadata_schema_version'),
                    registration.get('registration_hash'))

    try:
        with write_transaction() as session:
            require_capability(load_account_context(actor_id, session=session), 'clinician.write')
            from services.data_management_scope import assert_clinical_scope, assert_capture_id_available
            patient = session.query(Patient).filter_by(id=patient_id).with_for_update().one_or_none()
            assert_capture_id_available(session, capture_id)
            assert_clinical_scope(session, patient_id, capture_id=capture_id)
            device = session.query(Device).filter_by(device_code=payload['device_code']).first()
            if patient is None or device is None or patient.clinician_id != actor_id or device.clinician_id != actor_id:
                raise CollectionError(403)
            # Lock the old identity before checking retirement again. A create for
            # another patient must not race the old patient's delete transaction.
            existing = session.query(CollectionSession).filter_by(capture_id=capture_id).with_for_update().one_or_none()
            assert_capture_id_available(session, capture_id)
            if existing:
                if not same_request(existing, device):
                    raise CollectionError(409)
                return _capture_dto(existing)
            capture = CollectionSession(capture_id=capture_id, clinician_id=actor_id, patient_id=patient_id,
                device_id=device.id, mobile_started_at=started, server_created_at=server_now(), **registration)
            session.add(capture)
            session.flush()
            return _capture_dto(capture)
    except IntegrityError:
        # A concurrent create may win between SELECT and INSERT on InnoDB.
        with write_transaction() as session:
            capture = _owned_capture(session, capture_id, actor_id)
            device = session.get(Device, capture.device_id)
            if device.device_code != payload['device_code'] or not same_request(capture, device):
                raise CollectionError(409)
            return _capture_dto(capture)


def ingest_batch(actor_id, capture_id, payload):
    exact(payload, {'events'})
    events = payload['events']
    if not isinstance(events, list) or not 1 <= len(events) <= 100:
        raise CollectionError()
    events = [normalized_event(value) for value in events]
    if len({value['stream'] for value in events}) != 1:
        raise CollectionError()
    model = STREAM_MODELS[events[0]['stream']]
    try:
        with write_transaction() as session:
            capture = _owned_capture(session, capture_id, actor_id)
            results = []
            for value in events:
                received = value['received']
                if received < capture.mobile_started_at or (capture.mobile_stopped_at is not None and received > capture.mobile_stopped_at):
                    raise CollectionError(409)
                candidates = session.query(model).filter(model.capture_id == capture_id, or_(
                    model.event_id == value['event_id'],
                    (model.connection_epoch == value['connection_epoch']) & (model.stream_sequence == value['stream_sequence']))).all()
                if candidates:
                    if len(candidates) != 1 or candidates[0].payload_hash != value['digest']:
                        raise CollectionError(409)
                    row, status = candidates[0], 'duplicate'
                else:
                    if capture.final_counts_json is not None:
                        raise CollectionError(409)
                    now = server_now()
                    common = {key:value[key] for key in ('event_id','stream','stream_sequence','connection_epoch')}
                    common.update(capture_id=capture_id, mobile_received_at=received, server_received_at=now, payload_hash=value['digest'])
                    if model is CollectionInsoleFrame:
                        raw_clock = now + timedelta(hours=8)
                        raw_ids = []
                        for foot, fields in (('L',LEFT_FIELDS), ('R',RIGHT_FIELDS)):
                            raw = DeviceRawData(device_id=capture.device_id, patient_id=capture.patient_id,
                                clinician_id=actor_id, foot=foot, collected_at=raw_clock, uploaded_at=raw_clock,
                                **{dest:value['parsed'][source] for dest,source in fields.items()})
                            session.add(raw)
                            session.flush()
                            raw_ids.append(raw.id)
                        row = CollectionInsoleFrame(**common, left_raw_id=raw_ids[0], right_raw_id=raw_ids[1])
                        session.get(Patient, capture.patient_id).last_collected_at = raw_clock
                    elif model is CollectionGpsRaw:
                        row = CollectionGpsRaw(**common, **value['parsed'])
                    else:
                        parsed = value['parsed']
                        row = CollectionRadarRaw(**common, payload_json=json.dumps(parsed,ensure_ascii=False,allow_nan=False,separators=(',',':')),
                            **{key:parsed[key] for key in ('frames','bytes','age_ms','stale')})
                        row.targets = [CollectionRadarTarget(ordinal=index,**target) for index,target in enumerate(parsed['targets'])]
                    session.add(row)
                    session.flush()
                    status = 'accepted'
                results.append({'event_id':row.event_id,'stream':row.stream,'status':status,
                                'server_received_at':time_string(row.server_received_at)})
            return {'capture_id':capture_id,'results':results}
    except IntegrityError:
        raise CollectionError(409) from None


def stop_capture(actor_id, capture_id, payload, *, version=None):
    from services.collection_verification import verification_for_capture

    version = _request_version(payload, version)
    fields = {'mobile_stopped_at'}
    exact(payload, fields | {'schema_version', 'final_counts'} if version == 2 else fields)
    stopped = mobile_time(payload['mobile_stopped_at'])
    declared_counts = None
    if version == 2:
        counts = payload['final_counts']
        exact(counts, STREAM_MODELS)
        declared_counts = canonical_json_bytes({stream: integer(counts[stream]) for stream in STREAM_MODELS}).decode('utf-8')
    with write_transaction() as session:
        capture = _owned_capture(session, capture_id, actor_id)
        if (capture.metadata_schema_version == 1) != (version == 2):
            raise CollectionError(409)
        if stopped < capture.mobile_started_at:
            raise CollectionError(409)
        if capture.mobile_stopped_at is not None and capture.mobile_stopped_at != stopped:
            raise CollectionError(409)
        if capture.final_counts_json is not None and capture.final_counts_json != declared_counts:
            raise CollectionError(409)
        for model in STREAM_MODELS.values():
            if session.query(model.id).filter(model.capture_id == capture_id, model.mobile_received_at > stopped).first():
                raise CollectionError(409)
        if capture.mobile_stopped_at is None:
            capture.mobile_stopped_at = stopped
            capture.server_stopped_at = server_now()
        if version == 1:
            return _capture_dto(capture)
        capture.final_counts_json = declared_counts
        verification = verification_for_capture(session, capture, observed_at=capture.server_stopped_at)
        if capture.finalization_state is None:
            capture.finalization_state = verification['upload_state']
        return dict(_capture_dto(capture), verification=verification)
