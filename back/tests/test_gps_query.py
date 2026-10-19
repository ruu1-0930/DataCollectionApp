import pytest

from tests.test_collection_ingest import capture, event, gps_line, create, batch, stamp
from models.models import DeviceRawData
from services.gait_session_revision import _session_id


def gps_get(client, cap, **query):
    start = DeviceRawData.query.order_by(DeviceRawData.collected_at, DeviceRawData.id).first().collected_at
    sid = _session_id(cap['patient_id'], start)
    response = client.get(f"/patients/{cap['patient_id']}/gait/sessions/{sid}/gps", headers=cap['headers'], query_string=query)
    assert response.status_code == 200, response.get_json()
    return response.get_json()['data']


def seed_window(client, cap, end=10000):
    create(client, cap)
    assert batch(client, cap, [event(seq=0, ms=0), event(seq=1, ms=end)]).status_code == 200


@pytest.mark.parametrize('hdop,age,sats,fix,quality', [
    ('3','3500','4','1','good'), ('3.01','100','8','1','fair'), ('5','100','8','1','fair'),
    ('5.01','100','8','1','weak'), ('6','100','8','1','weak'), ('6.01','100','8','1','invalid'),
    ('1','3501','8','1','invalid'), ('1','100','3','1','invalid'), ('0','100','8','1','invalid'),
    ('1','100','8','0','invalid'),
])
def test_quality_boundaries(client, capture, hdop, age, sats, fix, quality):
    seed_window(client, capture)
    raw = gps_line(hdop=hdop, age=age, sats=sats, fix=fix)
    assert batch(client, capture, [event(stream='gps', payload={'raw_line': raw})]).status_code == 200
    data = gps_get(client, capture)
    assert data['items'][0]['quality'] == quality
    assert data['summary'][quality] == 1
    assert (data['items'][0]['segment_id'] is None) == (quality == 'invalid')


@pytest.mark.parametrize('offset,matched', [(1000, True), (1001, False)])
def test_nearest_receive_boundary_uses_explicit_raw_speeds(client, capture, offset, matched):
    seed_window(client, capture)
    assert batch(client, capture, [event(stream='gps', ms=offset)]).status_code == 200
    item = gps_get(client, capture)['items'][0]
    assert (item['insole_match'] is not None) == matched
    if matched:
        assert item['insole_match']['delta_ms'] == -offset
        assert item['insole_match']['left_speed'] == 1.1
        assert item['insole_match']['right_speed'] == 1.3
        assert item['speed'] == 1.2


def test_gap_epoch_and_overlapping_slice_union_are_stable(client, capture):
    create(client, capture)
    # Sequences 0,1 and 3,4 deliberately create overlapping receive windows.
    feet = [event(seq=0, ms=0), event(seq=1, ms=3000), event(seq=3, ms=1000), event(seq=4, ms=4000),
            event(seq=5, epoch=1, ms=0), event(seq=6, epoch=1, ms=4000)]
    assert batch(client, capture, feet).status_code == 200
    gps = [event(seq=0, stream='gps', ms=2000), event(seq=1, stream='gps', ms=3500),
           event(seq=0, epoch=1, stream='gps', ms=2000)]
    assert batch(client, capture, gps).status_code == 200
    data = gps_get(client, capture, page_size=2)
    assert len(data['collection_slices']) == 3
    assert data['total'] == 3 and data['summary']['total'] == 3
    assert len(data['items']) == 2
    all_items = data['items'] + gps_get(client, capture, page=2, page_size=2)['items']
    assert len({i['sample_id'] for i in all_items}) == 3
    assert len({i['segment_id'] for i in all_items}) == 3
    # First overlap belongs to first slice, so it cannot match the closer second slice frame.
    first = next(i for i in all_items if i['connection_epoch'] == 0 and i['stream_sequence'] == 0)
    assert first['insole_match']['event_id'] == feet[1]['event_id']


def test_invalid_gap_and_outlier_break_segments_without_rewriting_raw(client, capture):
    seed_window(client, capture, end=20000)
    gps = [event(seq=i, stream='gps', ms=ms, payload={'raw_line': gps_line(**over)})
           for i, (ms, over) in enumerate([(0, {}), (1000, {'fix':'0'}), (2000, {}),
                                         (8000, {}), (9000, {'lat':'32.23'}), (10000, {})])]
    assert batch(client, capture, gps).status_code == 200
    items = gps_get(client, capture)['items']
    assert items[1]['quality'] == 'invalid' and items[1]['segment_id'] is None
    assert items[4]['quality'] == 'invalid' and 'implausible_jump' in items[4]['reason_codes']
    assert items[4]['lat'] == 32.23
    assert len({items[i]['segment_id'] for i in (0,2,3,5)}) == 4


def test_unassociated_is_different_from_empty(client, capture):
    seed_window(client, capture)
    assert gps_get(client, capture)['availability'] == 'empty'
    from models.models import CollectionInsoleFrame
    CollectionInsoleFrame.query.delete()
    from config import db
    db.session.commit()
    assert gps_get(client, capture)['availability'] == 'unassociated'


def test_nearest_tie_chooses_earlier_receive_frame(client,capture):
    seed_window(client,capture,end=2000)
    assert batch(client,capture,[event(stream='gps',ms=1000)]).status_code == 200
    assert gps_get(client,capture)['items'][0]['insole_match']['mobile_received_at'] == stamp(0)


def test_gps_clock_regression_breaks_display_segment(client,capture):
    seed_window(client,capture,end=5000)
    samples = [event(seq=0,stream='gps',ms=0),event(seq=1,stream='gps',ms=3000),event(seq=2,stream='gps',ms=2000)]
    assert batch(client,capture,samples).status_code == 200
    items = gps_get(client,capture)['items']
    assert items[0]['segment_id'] != items[1]['segment_id']
    assert items[1]['segment_id'] != items[2]['segment_id']


def test_legacy_gap_scope_does_not_return_entire_capture(client,capture,db):
    from datetime import timedelta
    from models.models import CollectionInsoleFrame
    create(client,capture)
    assert batch(client,capture,[event(seq=0,ms=0),event(seq=1,ms=1000),event(seq=2,ms=2000),event(seq=3,ms=3000)]).status_code == 200
    frames = CollectionInsoleFrame.query.order_by(CollectionInsoleFrame.stream_sequence).all()
    raw_start = db.session.get(DeviceRawData,frames[0].left_raw_id).collected_at
    for frame in frames[2:]:
        for raw_id in (frame.left_raw_id,frame.right_raw_id):
            db.session.get(DeviceRawData,raw_id).collected_at = raw_start + timedelta(seconds=40)
    db.session.commit()
    assert batch(client,capture,[event(seq=0,stream='gps',ms=500),event(seq=1,stream='gps',ms=2500)]).status_code == 200
    data = gps_get(client,capture)
    assert data['total'] == 1
    assert data['collection_slices'][0]['mobile_to'] == stamp(1000)


def test_jump_still_invalid_when_receive_gap_also_breaks_line(client,capture):
    seed_window(client,capture,end=20000)
    assert batch(client,capture,[event(seq=0,stream='gps',ms=0),
        event(seq=1,stream='gps',ms=10000,payload={'raw_line':gps_line(lat='32.23')})]).status_code == 200
    assert gps_get(client,capture)['items'][1]['quality'] == 'invalid'
