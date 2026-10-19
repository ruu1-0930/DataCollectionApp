"""Atomic collection ingestion; mobile clocks never replace legacy raw clocks."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
import re
from uuid import UUID

from sqlalchemy import or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import db
from models.models import CollectionSession, CollectionInsoleFrame, CollectionGpsRaw, Device, Patient, DeviceRawData
from access import load_account_context, require_capability
from services.canonical_json import canonical_json_bytes, sha256_hex


SAFE_INTEGER = 9007199254740991
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
        if source == '':
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
    else:
        raise CollectionError()
    identity = {key:value[key] for key in ('event_id','stream','stream_sequence','connection_epoch','mobile_received_at')}
    digest = sha256_hex(canonical_json_bytes(dict(identity, payload=canonical_payload)))
    return dict(identity, received=received, parsed=parsed, digest=digest)


@contextmanager
def write_transaction():
    with Session(db.engine, expire_on_commit=False) as session:
        try:
            if db.engine.dialect.name == 'sqlite':
                session.execute(text('BEGIN IMMEDIATE'))
            else:
                session.begin()
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _owned_capture(session, capture_id, actor_id):
    identifier(capture_id)
    account = load_account_context(actor_id, session=session)
    require_capability(account, 'clinician.write')
    capture = session.query(CollectionSession).filter_by(capture_id=capture_id).with_for_update().first()
    if capture is None:
        raise CollectionError(404)
    if capture.clinician_id != actor_id:
        raise CollectionError(403)
    patient = session.get(Patient, capture.patient_id)
    device = session.get(Device, capture.device_id)
    if patient is None or device is None or patient.clinician_id != actor_id or device.clinician_id != actor_id:
        raise CollectionError(403)
    return capture


def _capture_dto(capture):
    return {'capture_id':capture.capture_id}


def create_capture(actor_id, payload):
    exact(payload, {'capture_id','patient_id','device_code','mobile_started_at'})
    capture_id = identifier(payload['capture_id'])
    patient_id = integer(payload['patient_id'])
    if patient_id < 1 or not isinstance(payload['device_code'], str) or not payload['device_code']:
        raise CollectionError()
    started = mobile_time(payload['mobile_started_at'])
    try:
        with write_transaction() as session:
            require_capability(load_account_context(actor_id, session=session), 'clinician.write')
            patient = session.get(Patient, patient_id)
            device = session.query(Device).filter_by(device_code=payload['device_code']).first()
            if patient is None or device is None or patient.clinician_id != actor_id or device.clinician_id != actor_id:
                raise CollectionError(403)
            existing = session.get(CollectionSession, capture_id)
            if existing:
                if (existing.clinician_id, existing.patient_id, existing.device_id, existing.mobile_started_at) != (actor_id,patient_id,device.id,started):
                    raise CollectionError(409)
                return _capture_dto(existing)
            capture = CollectionSession(capture_id=capture_id, clinician_id=actor_id, patient_id=patient_id,
                device_id=device.id, mobile_started_at=started, server_created_at=server_now())
            session.add(capture)
            session.flush()
            return _capture_dto(capture)
    except IntegrityError:
        # A concurrent create may win between SELECT and INSERT on InnoDB.
        with write_transaction() as session:
            capture = _owned_capture(session, capture_id, actor_id)
            device = session.get(Device, capture.device_id)
            if capture.patient_id != patient_id or device.device_code != payload['device_code'] or capture.mobile_started_at != started:
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
    model = CollectionInsoleFrame if events[0]['stream'] == 'insole' else CollectionGpsRaw
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
                    else:
                        row = CollectionGpsRaw(**common, **value['parsed'])
                    session.add(row)
                    session.flush()
                    status = 'accepted'
                results.append({'event_id':row.event_id,'stream':row.stream,'status':status,
                                'server_received_at':time_string(row.server_received_at)})
            return {'capture_id':capture_id,'results':results}
    except IntegrityError:
        raise CollectionError(409) from None


def stop_capture(actor_id, capture_id, payload):
    exact(payload, {'mobile_stopped_at'})
    stopped = mobile_time(payload['mobile_stopped_at'])
    with write_transaction() as session:
        capture = _owned_capture(session, capture_id, actor_id)
        if stopped < capture.mobile_started_at:
            raise CollectionError(409)
        if capture.mobile_stopped_at is not None and capture.mobile_stopped_at != stopped:
            raise CollectionError(409)
        for model in (CollectionInsoleFrame, CollectionGpsRaw):
            if session.query(model.id).filter(model.capture_id == capture_id, model.mobile_received_at > stopped).first():
                raise CollectionError(409)
        if capture.mobile_stopped_at is None:
            capture.mobile_stopped_at = stopped
            capture.server_stopped_at = server_now()
        return _capture_dto(capture)
