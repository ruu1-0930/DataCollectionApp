"""Shared sidecar windows, preserving the existing GPS association policy."""

from sqlalchemy import or_, select
from config import db
from models.models import CollectionSession, CollectionInsoleFrame, DeviceRawData


def build_collection_slices(patient_id, bounds):
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
