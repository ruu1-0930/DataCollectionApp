"""Read exact capture sources and the unclaimed rows of historical gap-v1 sessions."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from binascii import Error as Base64Error
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
from heapq import merge
from itertools import groupby, islice, zip_longest
import json
import re

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session, selectinload

from access import load_account_context, require_patient_scope
from api.gait import _foot_payload
from config import db
from models.models import CollectionGpsRaw, CollectionInsoleFrame, CollectionRadarRaw, CollectionSession, DeviceRawData, Patient
from services.canonical_json import canonical_json_bytes, sha256_hex
from services.collection_ingest import CollectionError, LEFT_FIELDS, STREAM_MODELS, identifier, server_now, time_string
from services.collection_slices import raw_has_capture
from services.collection_verification import verification_for_capture
from services.gait_analysis import REQUIRED_FIRMWARE_FIELDS, _finite_or_none
from services.gait_session_revision import _SESSION_GAP_SECONDS, _session_id, parse_session_start
from services.gps_query import capture_gps_item
from services.radar_query import capture_radar_item


LEGACY_TYPE = 'legacy_unspecified'
TEST_TYPES = {LEGACY_TYPE, 'static_standing', 'walk_10m_usual', 'five_times_sit_to_stand', 'tug', 'free_capture'}
CAPTURE_STATES = {'active', 'stopped', 'unknown'}
UPLOAD_STATES = {'pending', 'verified', 'mismatch', 'unknown'}
AGE_FILTERS = {'current_age_min', 'current_age_max', 'age_at_capture_min', 'age_at_capture_max'}
FILTER_FIELDS = AGE_FILTERS | {'patient_name', 'date_from', 'date_to', 'test_type', 'capture_state', 'upload_state'}
LEGACY_OFFSET = timedelta(hours=8)
LEGACY_GAP = timedelta(seconds=_SESSION_GAP_SECONDS)


@contextmanager
def _read_scope(actor, patient_id):
    # All SELECTs in one response see the same ingest state without locking capture writers.
    with db.engine.connect() as connection:
        dialect = connection.dialect.name
        if dialect == 'mysql':
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
        with Session(bind=connection) as session:
            if dialect == 'sqlite':
                session.execute(text('BEGIN'))
            account = load_account_context(actor.clinician_id, session=session)
            patient = session.get(Patient, patient_id)
            if patient is None:
                raise CollectionError(404)
            require_patient_scope(account, owner_id=patient.clinician_id, capability='clinical.read')
            from services.data_management_scope import assert_clinical_scope
            assert_clinical_scope(session, patient_id)
            yield session, patient, account.clinician_id if account.role == 'clinician' else None


def _when(value):
    return value.isoformat(timespec='microseconds') + 'Z' if value is not None else None


def _utc_legacy(value):
    return value - LEGACY_OFFSET if value is not None else None


def _parse_date(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
        raise CollectionError()
    try:
        # Use inclusive local dates without ending at midnight inside the selected day.
        return date.fromisoformat(value)
    except ValueError:
        raise CollectionError() from None


def _filters(values):
    if not isinstance(values, dict) or set(values) - FILTER_FIELDS:
        raise CollectionError()
    result = dict(values)
    for key in AGE_FILTERS & result.keys():
        value = result[key]
        if isinstance(value, str) and re.fullmatch(r'[0-9]{1,3}', value):
            value = int(value)
        if type(value) is not int or not 0 <= value <= 150:
            raise CollectionError()
        result[key] = value
    for low, high in (('current_age_min', 'current_age_max'), ('age_at_capture_min', 'age_at_capture_max')):
        if result.get(low, 0) > result.get(high, 150):
            raise CollectionError()
    for key, choices in (('test_type', TEST_TYPES), ('capture_state', CAPTURE_STATES), ('upload_state', UPLOAD_STATES)):
        if key in result and (not isinstance(result[key], str) or result[key] not in choices):
            raise CollectionError()
    if 'patient_name' in result:
        value = result['patient_name']
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 50:
            raise CollectionError()
        result['patient_name'] = value.strip().casefold()
    if 'date_from' in result or 'date_to' in result:
        try:
            start = datetime.combine(_parse_date(result['date_from']), time.min) - LEGACY_OFFSET if 'date_from' in result else None
            end = datetime.combine(_parse_date(result['date_to']), time.max) - LEGACY_OFFSET if 'date_to' in result else None
        except OverflowError:
            raise CollectionError() from None
        if start is not None and end is not None and end < start:
            raise CollectionError()
        if start is not None:
            result['date_from'] = start.isoformat()
        if end is not None:
            result['date_to'] = end.isoformat()
    return result


def _age_matches(value, filters, field):
    low, high = filters.get(field + '_min'), filters.get(field + '_max')
    if low is None and high is None:
        return True
    return value is not None and (low is None or value >= low) and (high is None or value <= high)


def _limit(value, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise CollectionError()
    return value


def _encode_cursor(scope, key):
    raw = canonical_json_bytes({'scope': scope, 'key': key})
    return urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode_cursor(value, scope):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', value):
        raise CollectionError()
    try:
        raw = urlsafe_b64decode(value + '=' * (-len(value) % 4))
        data = json.loads(raw)
        if set(data) != {'scope', 'key'} or data['scope'] != scope or _encode_cursor(scope, data['key']) != value:
            raise ValueError()
        return data['key']
    except (ValueError, KeyError, TypeError, OverflowError, Base64Error, UnicodeError):
        raise CollectionError() from None


def _cursor_time(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None or parsed.isoformat(timespec='microseconds') != value:
            raise ValueError()
        return parsed
    except (ValueError, TypeError):
        raise CollectionError() from None


def _directory_key(record):
    return record['started_at'], record['record_id']


def _capture_state(capture):
    return 'stopped' if capture.mobile_stopped_at is not None and capture.server_stopped_at is not None else 'active'


def _record_metadata(capture, verification, cutoff, technical_quality):
    registration = json.loads(capture.registration_json) if capture.registration_json is not None else None
    snapshot = registration['patient_snapshot'] if registration is not None else None
    stop = capture.mobile_stopped_at
    return dict(
        record_kind='capture', record_id=capture.capture_id, patient_id=capture.patient_id,
        test_type=capture.test_type or LEGACY_TYPE, patient_snapshot=snapshot,
        remarks=registration['remarks'] if registration is not None else None,
        age_at_capture=snapshot['age'] if snapshot is not None else None,
        started_at=_when(capture.mobile_started_at), ended_at=_when(stop),
        duration_s=(stop - capture.mobile_started_at).total_seconds() if stop is not None else None,
        recorded_through_at=_when(cutoff), capture_state=_capture_state(capture),
        upload_state=verification['upload_state'], received_counts=verification['received_counts'],
        record_version=verification['record_version'], technical_quality=technical_quality,
    )


def _capture_cutoff(session, capture_id, counts):
    through = [
        session.query(func.max(model.server_received_at)).filter(model.capture_id == capture_id).scalar()
        for stream, model in STREAM_MODELS.items() if counts[stream]
    ]
    return max((value for value in through if value is not None), default=None)


def _capture_records(session, patient_id, owner_id, filters, after):
    model = CollectionSession
    query = session.query(model).filter(model.patient_id == patient_id)
    if owner_id is not None:
        query = query.filter(model.clinician_id == owner_id)
    test_type = filters.get('test_type')
    if test_type is not None:
        query = query.filter(model.test_type.is_(None) if test_type == LEGACY_TYPE else model.test_type == test_type)
    if 'date_from' in filters:
        query = query.filter(model.mobile_started_at >= datetime.fromisoformat(filters['date_from']))
    if 'date_to' in filters:
        query = query.filter(model.mobile_started_at <= datetime.fromisoformat(filters['date_to']))
    if filters.get('capture_state') == 'unknown':
        return
    after = (datetime.fromisoformat(after[0].removesuffix('Z')), after[1]) if after is not None else None
    while True:
        page = query
        if after is not None:
            start, record_id = after
            page = page.filter(or_(model.mobile_started_at < start,
                                  and_(model.mobile_started_at == start, model.capture_id < record_id)))
        captures = page.order_by(model.mobile_started_at.desc(), model.capture_id.desc()).limit(100).all()
        if not captures:
            break
        for capture in captures:
            capture_state = _capture_state(capture)
            if filters.get('capture_state', capture_state) != capture_state:
                continue
            registration = json.loads(capture.registration_json) if capture.registration_json is not None else None
            age = registration['patient_snapshot']['age'] if registration is not None else None
            if not _age_matches(age, filters, 'age_at_capture'):
                continue
            verification = verification_for_capture(session, capture)
            if filters.get('upload_state', verification['upload_state']) != verification['upload_state']:
                continue
            cutoff = _capture_cutoff(session, capture.capture_id, verification['received_counts'])
            yield _record_metadata(capture, verification, cutoff, None)
        after = (captures[-1].mobile_started_at, captures[-1].capture_id)


def _raw_base(session, patient_id, columns):
    # A row with no legacy timestamp cannot establish or belong to a gap-v1 session.
    return session.query(*columns).filter(DeviceRawData.patient_id == patient_id,
                                          DeviceRawData.collected_at.is_not(None))


def _read_raw_chunks(query, *, reverse=False):
    model = DeviceRawData
    time_key, id_key = model.collected_at, model.id
    ordering = (time_key.desc(), id_key.desc()) if reverse else (time_key, id_key)
    query = query.order_by(*ordering)
    page = query
    while True:
        batch = page.limit(1000).all()
        if not batch:
            break
        yield from batch
        last = batch[-1]
        by_time = time_key < last.collected_at if reverse else time_key > last.collected_at
        by_id = id_key < last.id if reverse else id_key > last.id
        page = query.filter(or_(by_time, and_(time_key == last.collected_at, by_id)))


@dataclass
class _LegacySource:
    record_id: str
    start: datetime
    end: datetime
    cutoff: datetime | None
    frames: int
    version: str

    def counts(self):
        return dict(insole=self.frames, gps=0, radar=0)

    def verification(self):
        return dict(record_id=self.record_id, record_version=self.version, observed_at=time_string(server_now()),
                    expected_counts=None, received_counts=self.counts(),
                    upload_state='unknown', quality_observations=[])

    def record(self, patient_id, technical_quality=None):
        return dict(record_kind='legacy_session', record_id=self.record_id, patient_id=patient_id,
                    test_type=LEGACY_TYPE, patient_snapshot=None, remarks=None, age_at_capture=None,
                    started_at=_when(_utc_legacy(self.start)), ended_at=_when(_utc_legacy(self.end)),
                    duration_s=(self.end - self.start).total_seconds(), recorded_through_at=_when(_utc_legacy(self.cutoff)),
                    capture_state='unknown', upload_state='unknown', received_counts=self.counts(),
                    record_version=self.version, technical_quality=technical_quality)


def _legacy_sources(session, patient_id, owner_id, *, bounds=None):
    model = DeviceRawData
    legacy = ~raw_has_capture()
    if owner_id is not None:
        legacy = and_(legacy, model.clinician_id == owner_id)
    query = _raw_base(session, patient_id, (model.id, model.collected_at, model.uploaded_at, model.foot, legacy.label('legacy')))
    if bounds is not None:
        query = query.filter(model.collected_at.between(*bounds))
    elif query.filter(legacy).with_entities(model.id).first() is None:
        return

    # Partition by the original all-raw clock, then count and fingerprint only unclaimed rows.
    previous = start = end = cutoff = None
    frames = 0
    digest = sha256()
    for stamp, rows in groupby(_read_raw_chunks(query, reverse=True), key=lambda row: row.collected_at):
        if previous is None or previous - stamp > LEGACY_GAP:
            if frames:
                record_id = _session_id(patient_id, previous)
                version = sha256_hex(canonical_json_bytes([record_id, digest.hexdigest()]))
                yield _LegacySource(record_id, start, end, cutoff, frames, version)
            start = end = cutoff = None
            frames, digest = 0, sha256()
        left = right = 0
        for row in rows:
            if row.legacy:
                digest.update(f'{row.id}\n'.encode('ascii'))
                left += row.foot == 'L'
                right += row.foot == 'R'
                if row.uploaded_at is not None and (cutoff is None or row.uploaded_at > cutoff):
                    cutoff = row.uploaded_at
        if left or right:
            end = stamp if end is None else end
            start = stamp
            frames += max(left, right)
        previous = stamp
    if frames:
        record_id = _session_id(patient_id, previous)
        version = sha256_hex(canonical_json_bytes([record_id, digest.hexdigest()]))
        yield _LegacySource(record_id, start, end, cutoff, frames, version)


def _legacy_records(session, patient_id, owner_id, filters, after):
    if (filters.get('test_type', LEGACY_TYPE) != LEGACY_TYPE or filters.get('capture_state', 'unknown') != 'unknown'
            or filters.get('upload_state', 'unknown') != 'unknown' or not _age_matches(None, filters, 'age_at_capture')):
        return
    lower, upper = filters.get('date_from'), filters.get('date_to')
    for source in _legacy_sources(session, patient_id, owner_id):
        record = source.record(patient_id)
        timestamp = record['started_at'].removesuffix('Z')
        if lower is not None and datetime.fromisoformat(timestamp) < datetime.fromisoformat(lower):
            break
        if upper is not None and datetime.fromisoformat(timestamp) > datetime.fromisoformat(upper):
            continue
        if after is None or _directory_key(record) < after:
            yield record


def list_records(actor, patient_id, filters=None, cursor=None, limit=100):
    _limit(limit, 100)
    filters = _filters({} if filters is None else filters)
    scope = sha256_hex(canonical_json_bytes(['records', patient_id, filters]))
    after = _decode_cursor(cursor, scope)
    if after is not None:
        if not isinstance(after, list) or len(after) != 2 or not all(isinstance(value, str) for value in after):
            raise CollectionError()
        if not after[0].endswith('Z') or not 1 <= len(after[1]) <= 80:
            raise CollectionError()
        _cursor_time(after[0][:-1])
        after = tuple(after)
    with _read_scope(actor, patient_id) as (session, patient, owner_id):
        name_matches = 'patient_name' not in filters or (patient.pii is not None
                         and filters['patient_name'] in patient.pii.name.casefold())
        items = []
        if name_matches and _age_matches(patient.age, filters, 'current_age'):
            rows = merge(_capture_records(session, patient_id, owner_id, filters, after),
                         _legacy_records(session, patient_id, owner_id, filters, after),
                         key=_directory_key, reverse=True)
            items = list(islice(rows, limit + 1))
    next_cursor = _encode_cursor(scope, _directory_key(items[limit - 1])) if len(items) > limit else None
    return dict(patient_id=patient_id, items=items[:limit], next_cursor=next_cursor)


def _find_legacy(session, patient_id, owner_id, record_id):
    start = parse_session_start(patient_id, record_id)
    if start is None:
        raise CollectionError(404)
    model = DeviceRawData
    base = _raw_base(session, patient_id, (model.id, model.collected_at))
    prior = base.filter(model.collected_at < start).order_by(model.collected_at.desc()).first()
    if prior is not None and start - prior.collected_at <= LEGACY_GAP:
        raise CollectionError(404)
    end = start
    found = False
    for row in _read_raw_chunks(base.filter(model.collected_at >= start)):
        current = row.collected_at
        if (not found and current != start) or current - end > LEGACY_GAP:
            break
        found = True
        end = current
    if found:
        result = next(_legacy_sources(session, patient_id, owner_id, bounds=(start, end)), None)
        if result is not None:
            return result
    raise CollectionError(404)


def _source(session, patient_id, owner_id, record_id):
    from services.data_management_scope import assert_clinical_scope
    assert_clinical_scope(session, patient_id, record_id=record_id)
    if isinstance(record_id, str) and record_id.startswith('P'):
        return _find_legacy(session, patient_id, owner_id, record_id)
    identifier(record_id)
    capture = session.get(CollectionSession, record_id)
    if capture is None or capture.patient_id != patient_id:
        raise CollectionError(404)
    if owner_id is not None and capture.clinician_id != owner_id:
        raise CollectionError(403)
    return capture


def _raw_foot(row):
    if row is None:
        return None
    gait = _foot_payload({field: getattr(row, field) for field in LEFT_FIELDS})
    return dict(gait, raw_id=row.id, device_id=row.device_id,
                collected_at=_when(_utc_legacy(row.collected_at)),
                uploaded_at=_when(_utc_legacy(row.uploaded_at)))


def _capture_frame_rows(session, capture, after=0, limit=None, *, sequence_order=False):
    model = CollectionInsoleFrame
    frames = session.query(model).filter(model.capture_id == capture.capture_id, model.id > after)
    if sequence_order:
        frames = frames.order_by(model.connection_epoch, model.stream_sequence, model.id)
    else:
        frames = frames.order_by(model.id)
    if limit is not None:
        rows = frames.limit(limit).all()
        yield from _join_frame_feet(session, capture, rows)
        return
    # Keyset chunks in stream order preserve comparisons across query boundaries.
    query = frames
    while True:
        rows = query.limit(250).all()
        if not rows:
            break
        yield from _join_frame_feet(session, capture, rows)
        last = rows[-1]
        query = frames.filter(or_(model.connection_epoch > last.connection_epoch,
                                  and_(model.connection_epoch == last.connection_epoch, model.stream_sequence > last.stream_sequence)))


def _join_frame_feet(session, capture, frames):
    ids = {raw_id for frame in frames for raw_id in (frame.left_raw_id, frame.right_raw_id)}
    feet = {
        (row.id, row.foot): row
        for row in session.query(DeviceRawData).filter(DeviceRawData.id.in_(ids),
                DeviceRawData.patient_id == capture.patient_id,
                DeviceRawData.clinician_id == capture.clinician_id,
                DeviceRawData.device_id == capture.device_id)
    } if ids else {}
    for frame in frames:
        yield frame, feet.get((frame.left_raw_id, 'L')), feet.get((frame.right_raw_id, 'R'))


def _capture_frame(frame, left, right):
    return dict(frame_id=frame.id, event_id=frame.event_id, connection_epoch=frame.connection_epoch,
                stream_sequence=frame.stream_sequence, mobile_received_at=time_string(frame.mobile_received_at),
                server_received_at=time_string(frame.server_received_at),
                legacy_collected_at=None, left=_raw_foot(left), right=_raw_foot(right))


def _legacy_frame_rows(session, patient_id, owner_id, source, after=None):
    model = DeviceRawData
    query = _raw_base(session, patient_id, (model,)).filter(
        ~raw_has_capture(), model.collected_at.between(source.start, source.end))
    if owner_id is not None:
        query = query.filter(model.clinician_id == owner_id)
    if after is not None:
        query = query.filter(model.collected_at >= after[0])
    for stamp, rows in groupby(_read_raw_chunks(query), key=lambda row: row.collected_at):
        feet = {'L': [], 'R': []}
        for row in rows:
            if row.foot in feet:
                feet[row.foot].append(row)
        for ordinal, (left, right) in enumerate(zip_longest(feet['L'], feet['R'])):
            key = stamp, ordinal
            if after is None or key > after:
                yield key, left, right


def _legacy_frame(key, left, right):
    return dict(frame_id=None, event_id=None, connection_epoch=None, stream_sequence=None,
                mobile_received_at=None, server_received_at=None,
                legacy_collected_at=_when(_utc_legacy(key[0])), left=_raw_foot(left), right=_raw_foot(right))


def _quality(rows, *, capture):
    result = dict(left_raw_rows=0, right_raw_rows=0, frames_missing_left=0, frames_missing_right=0,
                  missing_required_values=0, mobile_time_regressions=None, insole_sequence_gaps=None)
    previous = None
    for frame, left, right in rows:
        result['left_raw_rows'] += left is not None
        result['right_raw_rows'] += right is not None
        result['frames_missing_left'] += left is None
        result['frames_missing_right'] += right is None
        result['missing_required_values'] += sum(
            row is None or _finite_or_none(getattr(row, field)) is None
            for row in (left, right) for field in REQUIRED_FIRMWARE_FIELDS
        )
        if capture and previous is not None and frame.connection_epoch == previous.connection_epoch:
            result['mobile_time_regressions'] = (result['mobile_time_regressions'] or 0) + (
                frame.mobile_received_at < previous.mobile_received_at)
            result['insole_sequence_gaps'] = (result['insole_sequence_gaps'] or 0) + (
                frame.stream_sequence > previous.stream_sequence + 1)
        previous = frame
    return result


def get_record(actor, patient_id, record_id):
    with _read_scope(actor, patient_id) as (session, _, owner_id):
        source = _source(session, patient_id, owner_id, record_id)
        if isinstance(source, _LegacySource):
            detail = _quality(_legacy_frame_rows(session, patient_id, owner_id, source), capture=False)
            return source.record(patient_id, detail)
        verification = verification_for_capture(session, source)
        cutoff = _capture_cutoff(session, record_id, verification['received_counts'])
        detail = _quality(_capture_frame_rows(session, source, sequence_order=True), capture=True)
        return _record_metadata(source, verification, cutoff, detail)


def get_record_verification(actor, patient_id, record_id):
    with _read_scope(actor, patient_id) as (session, _, owner_id):
        source = _source(session, patient_id, owner_id, record_id)
        return source.verification() if isinstance(source, _LegacySource) else verification_for_capture(session, source)


def _id_after(value):
    if value is None:
        return 0
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise CollectionError()
    return value


def _legacy_after(value):
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2 or type(value[1]) is not int or not 0 <= value[1] <= 2147483647:
        raise CollectionError()
    return _cursor_time(value[0]), value[1]


def _raw_page(record_id, version, page, limit, scope):
    next_cursor = _encode_cursor(scope, page[limit - 1][0]) if len(page) > limit else None
    return dict(record_id=record_id, record_version=version,
                items=[item for _, item in page[:limit]], next_cursor=next_cursor)


def list_record_frames(actor, patient_id, record_id, cursor=None, limit=500):
    _limit(limit, 500)
    scope = sha256_hex(canonical_json_bytes(['frames', patient_id, record_id]))
    after = _decode_cursor(cursor, scope)
    with _read_scope(actor, patient_id) as (session, _, owner_id):
        source = _source(session, patient_id, owner_id, record_id)
        if isinstance(source, _LegacySource):
            rows = _legacy_frame_rows(session, patient_id, owner_id, source, _legacy_after(after))
            page = [([key[0].isoformat(timespec='microseconds'), key[1]], _legacy_frame(key, left, right))
                    for key, left, right in islice(rows, limit + 1)]
            version = source.version
        else:
            rows = _capture_frame_rows(session, source, _id_after(after), limit + 1)
            page = [(frame.id, _capture_frame(frame, left, right)) for frame, left, right in rows]
            version = verification_for_capture(session, source)['record_version']
        return _raw_page(record_id, version, page, limit, scope)


def _list_sidecar(actor, patient_id, record_id, model, project, cursor, limit):
    _limit(limit, 500)
    scope = sha256_hex(canonical_json_bytes([model.__tablename__, patient_id, record_id]))
    after = _id_after(_decode_cursor(cursor, scope))
    with _read_scope(actor, patient_id) as (session, _, owner_id):
        source = _source(session, patient_id, owner_id, record_id)
        if isinstance(source, _LegacySource):
            return _raw_page(record_id, source.version, [], limit, scope)
        query = session.query(model).filter(model.capture_id == record_id, model.id > after)
        if model is CollectionRadarRaw:
            query = query.options(selectinload(CollectionRadarRaw.targets))
        rows = query.order_by(model.id).limit(limit + 1).all()
        page = [(row.id, project(row) if index < limit else None) for index, row in enumerate(rows)]
        return _raw_page(record_id, verification_for_capture(session, source)['record_version'], page, limit, scope)


def list_record_gps(actor, patient_id, record_id, cursor=None, limit=500):
    return _list_sidecar(actor, patient_id, record_id, CollectionGpsRaw, capture_gps_item, cursor, limit)


def list_record_radar(actor, patient_id, record_id, cursor=None, limit=500):
    return _list_sidecar(actor, patient_id, record_id, CollectionRadarRaw, capture_radar_item, cursor, limit)
