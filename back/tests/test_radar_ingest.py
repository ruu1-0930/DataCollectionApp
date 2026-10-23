from copy import deepcopy
from uuid import uuid4

from tests.test_collection_ingest import capture, create, batch, event, stamp
from tests.test_radar_protocol import radar_payload
from models.models import DeviceRawData, Patient


def radar_event(seq=0,ms=1000,epoch=7,**over):
    return event(seq=seq,ms=ms,epoch=epoch,stream='radar',payload=radar_payload(**over))


def test_radar_batch_retry_conflict_and_stop(client,capture,db):
    create(client,capture)
    sample = radar_event()
    assert batch(client,capture,[sample]).status_code == 200
    from models.models import CollectionRadarRaw, CollectionRadarTarget
    first = batch(client,capture,[sample]).get_json()['data']['results'][0]
    assert first['status'] == 'duplicate'
    changed = deepcopy(sample)
    changed['payload']['targets'][0]['x_mm'] = 12
    assert batch(client,capture,[radar_event(seq=1),changed]).status_code == 409
    assert CollectionRadarRaw.query.count() == CollectionRadarTarget.query.count() == 1
    assert DeviceRawData.query.count() == 0
    assert db.session.get(Patient,capture['patient_id']).last_collected_at is None
    path = '/collection-sessions/'+capture['capture_id']+'/stop'
    assert client.post(path,headers=capture['headers'],json={'mobile_stopped_at':stamp(999)}).status_code == 409
    assert client.post(path,headers=capture['headers'],json={'mobile_stopped_at':stamp(1000)}).status_code == 200
    assert batch(client,capture,[radar_event(seq=1,ms=1001)]).status_code == 409


def test_old_38_and_gps_payloads_unchanged(client,capture,db):
    from models.models import CollectionGpsRaw
    create(client,capture)
    sample = event()
    assert len(sample['payload']) == 38
    assert batch(client,capture,[sample]).status_code == 200
    rows = DeviceRawData.query.order_by(DeviceRawData.id).all()
    columns = [f'p{i}' for i in range(1,10)] + ['ax','ay','az','gx','gy','gz','step_length','walking_speed','single_support_time','double_support_time']
    for row,foot,expected in zip(rows,('L','R'),(
        [1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,1.1,18,19],
        [101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,1.3,118,119])):
        assert row.foot == foot
        assert [getattr(row,key) for key in columns] == expected
    gps = event(stream='gps')
    response = batch(client,capture,[gps])
    assert response.status_code == 200
    receipt = response.get_json()['data']['results'][0]
    assert set(receipt) == {'event_id','stream','status','server_received_at'}
    assert (receipt['event_id'],receipt['stream'],receipt['status']) == (gps['event_id'],'gps','accepted')
    assert CollectionGpsRaw.query.one().raw_line == gps['payload']['raw_line']


def test_radar_numeric_retry_and_order_preserved(client,capture):
    from models.models import CollectionRadarTarget
    create(client,capture)
    targets = [dict(radar_payload()['targets'][0],slot=s) for s in (3,1)]
    sample = radar_event(targets=targets,age_ms=1)
    assert batch(client,capture,[sample]).status_code == 200
    sample['payload']['age_ms'] = 1.0
    assert batch(client,capture,[sample]).get_json()['data']['results'][0]['status'] == 'duplicate'
    assert [t.slot for t in CollectionRadarTarget.query.order_by(CollectionRadarTarget.ordinal)] == [3,1]


def test_radar_database_constraints_reject_invalid_rows(client,capture,db):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from models.models import CollectionRadarRaw, CollectionRadarTarget
    create(client,capture)
    assert batch(client,capture,[radar_event()]).status_code == 200
    parent = CollectionRadarRaw.query.one()
    values = {c.name:getattr(parent,c.name) for c in CollectionRadarRaw.__table__.columns if c.name != 'id'}
    for field,bad in [('frames',-1),('bytes',9007199254740992),('connection_epoch',9007199254740992),('stream_sequence',-1),('age_ms',-1),('age_ms',float('inf'))]:
        change = dict(values,event_id=str(uuid4()),stream_sequence=22)
        change[field] = bad
        with pytest.raises(IntegrityError):
            db.session.execute(CollectionRadarRaw.__table__.insert().values(**change))
        db.session.rollback()
    child = CollectionRadarTarget.query.one()
    values = {c.name:getattr(child,c.name) for c in CollectionRadarTarget.__table__.columns if c.name != 'id'}
    for over in [dict(slot=4,ordinal=1),dict(slot=2,ordinal=3),dict(slot=2,ordinal=1,x_mm=32768),dict(slot=2,ordinal=1,resolution_mm=65536),dict(slot=3,ordinal=1),dict(slot=2,ordinal=0)]:
        with pytest.raises(IntegrityError):
            db.session.execute(CollectionRadarTarget.__table__.insert().values(**dict(values,**over)))
        db.session.rollback()
