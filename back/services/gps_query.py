"""Read-only GPS association and gps-display-v1 presentation policy."""

import math
from sqlalchemy import or_, select

from config import db
from models.models import CollectionSession, CollectionInsoleFrame, CollectionGpsRaw, DeviceRawData, Patient
from access import require_patient_scope
from services.collection_ingest import CollectionError, time_string
from services.gait_session_revision import parse_session_start
from api.gait import _session_bounds_for_start


GPS_FIELDS = ('event_id','capture_id','connection_epoch','stream_sequence','raw_line','seq','fix',
              'lat','lon','alt','speed','sats','hdop','age','utc','chars','errors')


def quality(row):
    reasons = []
    if not row.fix:
        reasons.append('no_fix')
    if row.lat is None or row.lon is None or not -90 <= row.lat <= 90 or not -180 <= row.lon <= 180:
        reasons.append('invalid_coordinates')
    if row.sats < 4:
        reasons.append('insufficient_satellites')
    if not 0 <= row.age <= 3500:
        reasons.append('stale_fix')
    if row.hdop is None or not 0 < row.hdop <= 6:
        reasons.append('invalid_hdop')
    if reasons:
        return 'invalid', reasons
    return ('good' if row.hdop <= 3 else 'fair' if row.hdop <= 5 else 'weak'), []


def _distance(first, second):
    lat1, lat2 = math.radians(first.lat), math.radians(second.lat)
    dlat, dlon = lat2-lat1, math.radians(second.lon-first.lon)
    hav = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, hav))))


def _slices(patient_id, bounds):
    raw_ids = select(DeviceRawData.id).where(DeviceRawData.patient_id == patient_id,
        DeviceRawData.collected_at >= bounds[0], DeviceRawData.collected_at <= bounds[1])
    frames = (db.session.query(CollectionInsoleFrame, CollectionSession)
        .join(CollectionSession, CollectionSession.capture_id == CollectionInsoleFrame.capture_id)
        .filter(CollectionSession.patient_id == patient_id,
                or_(CollectionInsoleFrame.left_raw_id.in_(raw_ids), CollectionInsoleFrame.right_raw_id.in_(raw_ids)))
        .order_by(CollectionInsoleFrame.capture_id, CollectionInsoleFrame.connection_epoch,
                  CollectionInsoleFrame.stream_sequence, CollectionInsoleFrame.id).all())
    slices = []
    for frame, capture in frames:
        previous = slices[-1]['_frames'][-1] if slices else None
        if (previous is None or previous.capture_id != frame.capture_id
                or previous.connection_epoch != frame.connection_epoch
                or previous.stream_sequence + 1 != frame.stream_sequence
                or frame.mobile_received_at < previous.mobile_received_at):
            slices.append({'capture_id':frame.capture_id,'device_id':capture.device_id,
                'connection_epoch':frame.connection_epoch,'mobile_from':frame.mobile_received_at,
                'mobile_to':frame.mobile_received_at,'_frames':[],'_first_id':frame.id})
        slices[-1]['_frames'].append(frame)
        slices[-1]['mobile_to'] = frame.mobile_received_at
    return sorted(slices, key=lambda s:(s['capture_id'],s['connection_epoch'],s['mobile_from'],s['mobile_to'],s['_first_id']))


def _nearest(row, frames, raw_speeds):
    nearest = min(frames, key=lambda f:(abs((f.mobile_received_at-row.mobile_received_at).total_seconds()), f.mobile_received_at, f.id))
    delta = nearest.mobile_received_at-row.mobile_received_at
    delta_ms = delta.days*86400000 + delta.seconds*1000 + delta.microseconds//1000
    if abs(delta_ms) > 1000:
        return None
    def speed(raw_id):
        value = raw_speeds.get(raw_id)
        return value if value is not None and math.isfinite(value) else None
    return {'event_id':nearest.event_id,'mobile_received_at':time_string(nearest.mobile_received_at),
        'delta_ms':delta_ms,'left_speed':speed(nearest.left_raw_id),'right_speed':speed(nearest.right_raw_id)}


def session_gps(account, patient_id, session_id, page=1, page_size=500):
    patient = db.session.get(Patient, patient_id)
    if patient is None:
        raise CollectionError(404)
    require_patient_scope(account, owner_id=patient.clinician_id, capability='clinical.read')
    start = parse_session_start(patient_id, session_id)
    if start is None:
        raise CollectionError(422)
    bounds = _session_bounds_for_start(patient_id, start)
    if bounds is None:
        raise CollectionError(404)
    slices = _slices(patient_id, bounds)
    summary = {key:0 for key in ('total','good','fair','weak','invalid')}
    result = dict(schema_version='gps-session-v1',patient_id=patient_id,session_id=session_id,
        availability='empty' if slices else 'unassociated',clock_basis='mobile_receive_not_hardware_sync',
        collection_slices=[{key:time_string(value) if key.startswith('mobile_') else value
            for key,value in s.items() if not key.startswith('_')} for s in slices],
        summary=summary,page=page,page_size=page_size,total=0,items=[])
    if not slices:
        return result
    conditions = [(CollectionGpsRaw.capture_id == s['capture_id']) &
        (CollectionGpsRaw.connection_epoch == s['connection_epoch']) &
        (CollectionGpsRaw.mobile_received_at >= s['mobile_from']) &
        (CollectionGpsRaw.mobile_received_at <= s['mobile_to']) for s in slices]
    rows = db.session.query(CollectionGpsRaw).filter(or_(*conditions)).order_by(CollectionGpsRaw.mobile_received_at,CollectionGpsRaw.id).all()
    # SQL OR yields one row per raw sample, even when multiple slice predicates match.
    owned_rows = [[] for _ in slices]
    for row in rows:
        for index,s in enumerate(slices):
            if row.capture_id == s['capture_id'] and row.connection_epoch == s['connection_epoch'] and s['mobile_from'] <= row.mobile_received_at <= s['mobile_to']:
                owned_rows[index].append(row)
                break
    raw_ids = {raw_id for s in slices for f in s['_frames'] for raw_id in (f.left_raw_id,f.right_raw_id)}
    raw_speeds = dict(db.session.query(DeviceRawData.id,DeviceRawData.walking_speed).filter(DeviceRawData.id.in_(raw_ids)).all())
    items = []
    for index,(s,samples) in enumerate(zip(slices,owned_rows)):
        previous, segment_number = None, 0
        by_sequence = sorted(samples,key=lambda r:(r.stream_sequence,r.id))
        regressions = {current.id for prior,current in zip(by_sequence,by_sequence[1:])
                       if current.mobile_received_at < prior.mobile_received_at}
        for row in samples:
            label,reasons = quality(row)
            gap = (row.mobile_received_at-previous.mobile_received_at).total_seconds() if previous else None
            if label != 'invalid' and previous and gap is not None and gap >= 0:
                distance = _distance(previous,row)
                if (gap == 0 and distance > 0) or (gap > 0 and distance/gap > 60):
                    label,reasons = 'invalid',['implausible_jump']
            item = {key:getattr(row,key) for key in GPS_FIELDS}
            item.update(sample_id=row.id,mobile_received_at=time_string(row.mobile_received_at),
                server_received_at=time_string(row.server_received_at),quality=label,reason_codes=reasons,
                segment_id=None,insole_match=_nearest(row,s['_frames'],raw_speeds))
            if label == 'invalid':
                previous = None
            else:
                if previous is None or gap is None or gap > 5 or gap < 0 or row.id in regressions or row.stream_sequence <= previous.stream_sequence:
                    segment_number += 1
                item['segment_id'] = f'{index + 1}:{segment_number}'
                previous = row
            summary[label] += 1
            items.append(item)
    items.sort(key=lambda i:(i['mobile_received_at'],i['sample_id']))
    summary['total'] = result['total'] = len(items)
    result['availability'] = 'available' if items else 'empty'
    result['items'] = items[(page-1)*page_size:page*page_size]
    return result
