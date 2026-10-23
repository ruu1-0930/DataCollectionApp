from uuid import uuid4
from tests.test_collection_ingest import capture, create, batch, event, stamp
from tests.test_radar_ingest import radar_event
from models.models import DeviceRawData
from services.gait_session_revision import _session_id


def radar_path(cap):
    start = DeviceRawData.query.order_by(DeviceRawData.collected_at,DeviceRawData.id).first().collected_at
    return f"/patients/{cap['patient_id']}/gait/sessions/{_session_id(cap['patient_id'],start)}/radar"


def radar_get(client,cap,**query):
    response = client.get(radar_path(cap),headers=cap['headers'],query_string=query)
    assert response.status_code == 200, response.get_json()
    return response.get_json()['data']


def window(client,cap,end=20000):
    create(client,cap)
    assert batch(client,cap,[event(seq=0,ms=0,epoch=2),event(seq=1,ms=end,epoch=2)]).status_code == 200


def test_radar_independent_epoch_and_slice_boundaries(client,capture):
    window(client,capture,end=4000)
    assert batch(client,capture,[radar_event(seq=0,ms=0),radar_event(seq=1,ms=4000,frames=2),radar_event(seq=2,ms=4001)]).status_code == 200
    other = dict(capture,capture_id=str(uuid4()),body=dict(capture['body'],capture_id=str(uuid4())))
    other['body']['capture_id'] = other['capture_id']
    create(client,other)
    assert batch(client,other,[radar_event()]).status_code == 200
    data = radar_get(client,capture)
    assert data['total'] == 2
    assert data['collection_slices'][0]['connection_epoch'] == 2
    assert {item['connection_epoch'] for item in data['items']} == {7}
    assert {item['slice_index'] for item in data['items']} == {1}


def test_repeated_frames_do_not_extend_track(client,capture):
    window(client,capture)
    samples = [radar_event(seq=0,ms=0),radar_event(seq=1,ms=2900),radar_event(seq=2,ms=3100,frames=2)]
    assert batch(client,capture,samples).status_code == 200
    items = radar_get(client,capture)['items']
    assert [item['repeat_frame'] for item in items] == [False,True,False]
    assert items[0]['target_views'][0]['segment_id'] == items[1]['target_views'][0]['segment_id']
    assert items[0]['target_views'][0]['segment_id'] != items[2]['target_views'][0]['segment_id']


def test_quality_segments_and_pagination_are_global(client,capture):
    window(client,capture)
    samples = [radar_event(seq=i,ms=i*1000,**over) for i,over in enumerate([
        {},dict(frames=2,age_ms=None),dict(frames=3),dict(frames=4,targets=[]),dict(frames=5),
        dict(frames=6,stale=True),dict(frames=7),dict(frames=8,bytes=1),dict(frames=9,bytes=2),
        dict(frames=0,age_ms=1501,stale=True),dict(frames=10,age_ms=1500)])]
    assert batch(client,capture,samples).status_code == 200
    whole = radar_get(client,capture)
    pages = [radar_get(client,capture,page=i,page_size=3) for i in range(1,5)]
    assert [item for p in pages for item in p['items']] == whole['items']
    assert all(p['summary'] == whole['summary'] for p in pages)
    assert whole['summary'] == dict(total=11,fresh=7,stale=3,empty=1)
    assert whole['items'][9]['reason_codes'] == ['no_frames','reported_stale','age_exceeded']
    assert whole['items'][1]['target_views'][0] == dict(slot=3,display_valid=False,segment_id=None)
    assert whole['items'][6]['target_views'][0]['segment_id'] != whole['items'][7]['target_views'][0]['segment_id']


def test_read_has_no_business_writes(client,capture,db):
    from sqlalchemy import event as sql_event
    window(client,capture)
    assert batch(client,capture,[radar_event()]).status_code == 200
    writes = []
    def watch(_conn,_cursor,statement,*_):
        if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):
            writes.append(statement)
    sql_event.listen(db.engine,'before_cursor_execute',watch)
    try:
        assert radar_get(client,capture)['total'] == 1
    finally:
        sql_event.remove(db.engine,'before_cursor_execute',watch)
    assert writes == []


def test_slot_disappearance_counter_reset_epoch_and_three_second_boundary(client,capture):
    window(client,capture,end=30000)
    source = radar_event()['payload']['targets'][0]
    samples = [radar_event(seq=0,ms=0),radar_event(seq=1,ms=3000,frames=2),
        radar_event(seq=2,ms=6001,frames=3),radar_event(seq=3,ms=7000,frames=4,targets=[dict(source,present=False)]),
        radar_event(seq=4,ms=8000,frames=5),radar_event(seq=5,ms=9000,frames=1),
        radar_event(seq=0,ms=10000,epoch=8,frames=2)]
    assert batch(client,capture,samples).status_code == 200
    items = radar_get(client,capture)['items']
    ids = [i['target_views'][0]['segment_id'] for i in items]
    assert ids[0] == ids[1]
    assert ids[1] != ids[2] and ids[3] is None
    assert len({ids[i] for i in (2,4,5,6)}) == 4


def test_overlapping_slices_assign_once_and_old_raw_is_unassociated(client,capture,db):
    from models.models import CollectionInsoleFrame
    create(client,capture)
    assert batch(client,capture,[event(seq=0,ms=0,epoch=2),event(seq=1,ms=3000,epoch=2),
        event(seq=3,ms=1000,epoch=2),event(seq=4,ms=4000,epoch=2)]).status_code == 200
    assert batch(client,capture,[radar_event(ms=2000)]).status_code == 200
    data = radar_get(client,capture)
    assert len(data['collection_slices']) == 2 and data['total'] == 1
    assert data['items'][0]['slice_index'] == 1
    CollectionInsoleFrame.query.delete()
    db.session.commit()
    data = radar_get(client,capture)
    assert data['availability'] == 'unassociated' and data['items'] == []


def test_radar_clock_regression_is_a_segment_boundary(client,capture):
    window(client,capture,end=10000)
    assert batch(client,capture,[radar_event(seq=0,ms=0),radar_event(seq=1,ms=3000,frames=2),radar_event(seq=2,ms=2000,frames=3)]).status_code == 200
    items = radar_get(client,capture)['items']
    assert len({item['target_views'][0]['segment_id'] for item in items}) == 3


def test_large_finite_age_preserves_raw_payload_and_conflict_identity(client,capture):
    from copy import deepcopy
    window(client,capture)
    sample = radar_event(age_ms=10**30+1)
    assert batch(client,capture,[sample]).status_code == 200
    assert radar_get(client,capture)['items'][0]['payload'] == sample['payload']
    changed = deepcopy(sample)
    changed['payload']['age_ms'] += 1
    assert batch(client,capture,[changed]).status_code == 409


def test_radar_audit_read_rejects_payload_or_normalized_corruption(client,capture,db):
    import json
    from models.models import CollectionRadarRaw, CollectionRadarTarget
    window(client,capture)
    sample = radar_event(age_ms=0.1234567890123456)
    assert batch(client,capture,[sample]).status_code == 200
    assert radar_get(client,capture)['items'][0]['payload'] == sample['payload']
    parent = CollectionRadarRaw.query.one()
    original = parent.payload_json
    parent.payload_json = json.dumps(dict(sample['payload'],frames=42))
    db.session.commit()
    assert client.get(radar_path(capture),headers=capture['headers']).status_code == 503
    parent.payload_json = original
    db.session.commit()
    child = CollectionRadarTarget.query.one()
    child.x_mm = 100
    db.session.commit()
    assert client.get(radar_path(capture),headers=capture['headers']).status_code == 503
