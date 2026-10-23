"""Read-only radar-session-v1 association and per-slot display segments."""

import json
from sqlalchemy import or_
from sqlalchemy.orm import selectinload
from config import db
from access import require_patient_scope
from models.models import CollectionRadarRaw, Patient
from services.collection_ingest import CollectionError, time_string, normalized_event
from services.collection_slices import build_collection_slices
from services.gait_session_revision import parse_session_start
from api.gait import _session_bounds_for_start


def _quality(row):
    reasons = []
    if row.frames == 0:
        reasons.append('no_frames')
    if row.stale:
        reasons.append('reported_stale')
    if row.age_ms is None:
        reasons.append('age_missing')
    elif row.age_ms > 1500:
        reasons.append('age_exceeded')
    return ('stale' if reasons else 'fresh' if any(t.present for t in row.targets) else 'empty'), reasons


def _verified_payload(row):
    # DOUBLE supports quality filtering but cannot retain every finite JSON integer.
    # Audit reads verify the retained numeric value and the normalized projection.
    def unique(pairs):
        result = {}
        for key,value in pairs:
            if key in result:
                raise ValueError('duplicate field')
            result[key] = value
        return result
    try:
        payload = json.loads(row.payload_json,object_pairs_hook=unique)
        identity = {key:getattr(row,key) for key in ('event_id','stream','connection_epoch','stream_sequence')}
        identity.update(mobile_received_at=time_string(row.mobile_received_at),payload=payload)
        parsed = normalized_event(identity)
        if parsed['digest'] != row.payload_hash:
            raise ValueError('hash mismatch')
        if any(payload[key] != getattr(row,key) for key in ('frames','bytes','stale')):
            raise ValueError('counter mismatch')
        age = payload['age_ms']
        if (None if age is None else float(age)) != row.age_ms:
            raise ValueError('age mismatch')
        targets = [{key:getattr(t,key) for key in ('slot','present','x_mm','y_mm','speed_cms','resolution_mm')} for t in row.targets]
        if targets != payload['targets'] or [t.ordinal for t in row.targets] != list(range(len(targets))):
            raise ValueError('target mismatch')
        return payload
    except (ValueError,TypeError,OverflowError):
        # Corrupt stored evidence is a service failure, never a client error or a
        # partially trusted display observation. No repair is performed on reads.
        raise CollectionError(503) from None


def session_radar(account, patient_id, session_id, page=1, page_size=500):
    patient = db.session.get(Patient,patient_id)
    if patient is None:
        raise CollectionError(404)
    require_patient_scope(account,owner_id=patient.clinician_id,capability='clinical.read')
    start = parse_session_start(patient_id,session_id)
    if start is None:
        raise CollectionError(422)
    bounds = _session_bounds_for_start(patient_id,start)
    if bounds is None:
        raise CollectionError(404)
    slices = build_collection_slices(patient_id,bounds)
    summary = dict(total=0,fresh=0,stale=0,empty=0)
    result = dict(schema_version='radar-session-v1',patient_id=patient_id,session_id=session_id,
        availability='empty' if slices else 'unassociated',clock_basis='mobile_receive_not_hardware_sync',
        collection_slices=[{key:time_string(value) if key.startswith('mobile_') else value
            for key,value in s.items() if not key.startswith('_')} for s in slices],
        summary=summary,page=page,page_size=page_size,total=0,items=[])
    if not slices:
        return result
    conditions = [(CollectionRadarRaw.capture_id == s['capture_id']) &
        (CollectionRadarRaw.mobile_received_at >= s['mobile_from']) &
        (CollectionRadarRaw.mobile_received_at <= s['mobile_to']) for s in slices]
    rows = (db.session.query(CollectionRadarRaw).options(selectinload(CollectionRadarRaw.targets))
        .filter(or_(*conditions)).order_by(CollectionRadarRaw.mobile_received_at,CollectionRadarRaw.id).all())
    owned = [[] for _ in slices]
    for row in rows:
        for index,s in enumerate(slices):
            if row.capture_id == s['capture_id'] and s['mobile_from'] <= row.mobile_received_at <= s['mobile_to']:
                owned[index].append(row)
                break
    items = []
    for index,samples in enumerate(owned):
        # Derive regression fences in stream order before display-time sorting.
        regressions = set()
        for epoch in {r.connection_epoch for r in samples}:
            ordered = sorted((r for r in samples if r.connection_epoch == epoch),key=lambda r:(r.stream_sequence,r.id))
            regressions.update(cur.id for prev,cur in zip(ordered,ordered[1:]) if cur.mobile_received_at < prev.mobile_received_at)
        previous = None
        last_points, counters = {}, {slot:0 for slot in (1,2,3)}
        for row in samples:
            payload = _verified_payload(row)
            label,reasons = _quality(row)
            changed_epoch = previous is not None and row.connection_epoch != previous.connection_epoch
            reset = previous is not None and (row.frames < previous.frames or row.bytes < previous.bytes)
            fence = changed_epoch or reset or row.id in regressions or (previous is not None and row.stream_sequence <= previous.stream_sequence)
            repeat = previous is not None and not fence and row.frames == previous.frames
            if fence or label == 'stale':
                last_points.clear()
            present_slots = {t.slot for t in row.targets if t.present}
            for slot in set(last_points)-present_slots:
                last_points.pop(slot)
            views = []
            for target in row.targets:
                valid = label != 'stale' and target.present
                segment = None
                if valid:
                    prior = last_points.get(target.slot)
                    gap = (row.mobile_received_at-prior[0]).total_seconds() if prior else None
                    if repeat:
                        segment = prior[1] if prior and gap <= 3 else None
                    else:
                        if prior is None or gap > 3 or gap < 0:
                            counters[target.slot] += 1
                        segment = f'{index+1}:{row.connection_epoch}:{target.slot}:{counters[target.slot]}'
                        last_points[target.slot] = (row.mobile_received_at,segment)
                views.append(dict(slot=target.slot,display_valid=valid,segment_id=segment))
            item = {key:getattr(row,key) for key in ('event_id','capture_id','connection_epoch','stream_sequence')}
            item.update(sample_id=row.id,mobile_received_at=time_string(row.mobile_received_at),server_received_at=time_string(row.server_received_at),
                slice_index=index+1,payload=payload,quality=label,reason_codes=reasons,repeat_frame=repeat,target_views=views)
            summary[label] += 1
            items.append(item)
            previous = row
    items.sort(key=lambda item:(item['mobile_received_at'],item['sample_id']))
    result['total'] = summary['total'] = len(items)
    result['availability'] = 'available' if items else 'empty'
    result['items'] = items[(page-1)*page_size:page*page_size]
    return result
