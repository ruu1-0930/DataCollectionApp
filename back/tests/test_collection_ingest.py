from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from models.models import DeviceRawData, DeviceTransformedData
from tests.test_raw_data import _frame, _setup


def stamp(ms=0):
    return (datetime(2026, 10, 19, 0, 0) + timedelta(milliseconds=ms)).isoformat(timespec='milliseconds') + 'Z'


@pytest.fixture
def capture(client, monkeypatch):
    import api.device
    monkeypatch.setattr(api.device, 'analyze', lambda *_: (_ for _ in ()).throw(AssertionError('SVM called')))
    headers, patient_id = _setup(client)
    capture_id = str(uuid4())
    body = dict(capture_id=capture_id, patient_id=patient_id, device_code='INSOLE-001', mobile_started_at=stamp())
    return dict(headers=headers, patient_id=patient_id, capture_id=capture_id, body=body)


def event(seq=0, ms=1000, stream='insole', epoch=0, **over):
    payload = _frame(left_speed=1.1, right_speed=1.3) if stream == 'insole' else {'raw_line': gps_line()}
    result = dict(event_id=str(uuid4()), stream=stream, stream_sequence=seq,
                  connection_epoch=epoch, mobile_received_at=stamp(ms), payload=payload)
    result.update(over)
    return result


def gps_line(**over):
    fields = dict(seq='12', fix='1', lat='31.2300000', lon='121.4700000', alt='12.0',
                  speed='1.20', sats='8', hdop='1.10', age='100', utc='2026-10-15T12:00:00Z', chars='5000', errors='0')
    fields.update(over)
    return 'GPS1,' + ','.join(fields.values())


def create(client, cap):
    response = client.post('/collection-sessions', headers=cap['headers'], json=cap['body'])
    assert response.status_code == 200, response.get_json()
    return response.get_json()['data']


def batch(client, cap, events):
    return client.post('/collection-sessions/' + cap['capture_id'] + '/batches',
                       headers=cap['headers'], json={'events': events})


def test_create_is_idempotent_and_identity_is_frozen(client, capture):
    assert create(client, capture) == create(client, capture)
    changed = dict(capture['body'], mobile_started_at=stamp(1))
    assert client.post('/collection-sessions', headers=capture['headers'], json=changed).status_code == 409


def test_batch_duplicate_preserves_two_raw_rows_and_uses_no_svm(client, capture, db):
    from models.models import CollectionInsoleFrame
    create(client, capture)
    sample = event()
    first = batch(client, capture, [sample])
    assert first.status_code == 200
    assert first.get_json()['data']['results'][0]['status'] == 'accepted'
    second = batch(client, capture, [sample])
    assert second.get_json()['data']['results'][0]['status'] == 'duplicate'
    assert first.get_json()['data']['results'][0]['server_received_at'] == second.get_json()['data']['results'][0]['server_received_at']
    assert DeviceRawData.query.count() == 2
    assert DeviceTransformedData.query.count() == 0
    sidecar = CollectionInsoleFrame.query.one()
    assert db.session.get(DeviceRawData, sidecar.left_raw_id).foot == 'L'
    assert db.session.get(DeviceRawData, sidecar.right_raw_id).foot == 'R'
    assert sidecar.mobile_received_at != db.session.get(DeviceRawData, sidecar.left_raw_id).collected_at


@pytest.mark.parametrize('key', ['event', 'sequence'])
def test_conflict_rolls_back_entire_batch(client, capture, key):
    create(client, capture)
    old = event()
    assert batch(client, capture, [old]).status_code == 200
    conflict = deepcopy(old)
    if key == 'sequence':
        conflict['event_id'] = str(uuid4())
    conflict['payload']['left_speed'] = 99
    assert batch(client, capture, [event(seq=1), conflict]).status_code == 409
    assert DeviceRawData.query.count() == 2


def test_stopped_window_allows_delayed_and_rejects_outside(client, capture):
    create(client, capture)
    stop_path = '/collection-sessions/' + capture['capture_id'] + '/stop'
    for _ in range(2):
        assert client.post(stop_path, headers=capture['headers'], json={'mobile_stopped_at': stamp(5000)}).status_code == 200
    assert batch(client, capture, [event(ms=5000)]).status_code == 200
    assert batch(client, capture, [event(seq=1, ms=5001)]).status_code == 409
    assert client.post(stop_path, headers=capture['headers'], json={'mobile_stopped_at': stamp(6000)}).status_code == 409


def test_stop_cannot_precede_existing_samples(client, capture):
    create(client, capture)
    assert batch(client, capture, [event(ms=5000)]).status_code == 200
    assert client.post('/collection-sessions/' + capture['capture_id'] + '/stop', headers=capture['headers'],
                       json={'mobile_stopped_at': stamp(4999)}).status_code == 409


def test_null_no_fix_and_firmware_seq_reset_are_preserved(client, capture):
    from models.models import CollectionGpsRaw
    create(client, capture)
    raw = gps_line(fix='0', lat='', lon='', alt='', speed='', hdop='', utc='')
    samples = [event(seq=i, epoch=i, stream='gps', payload={'raw_line': raw}) for i in range(2)]
    assert batch(client, capture, samples).status_code == 200
    rows = CollectionGpsRaw.query.all()
    assert len(rows) == 2 and rows[0].raw_line == raw
    assert rows[0].lat is None and rows[0].speed is None and rows[0].utc == ''
    assert rows[0].seq == rows[1].seq == 12


@pytest.mark.parametrize('change', [
    lambda e: e.update(stream_sequence=True), lambda e: e.update(connection_epoch=-1),
    lambda e: e.update(extra=1), lambda e: e.update(mobile_received_at='2026-10-19T00:00:01Z'),
    lambda e: e['payload'].update(left_speed=float('nan')),
    lambda e: e['payload'].update(left_speed=10**309),
])
def test_strict_event_validation(client, capture, change):
    create(client, capture)
    sample = event()
    change(sample)
    assert batch(client, capture, [sample]).status_code == 400
    assert DeviceRawData.query.count() == 0


def test_invalid_gps_batch_does_not_poison_separate_insole_batch(client, capture):
    create(client, capture)
    bad = event(stream='gps', payload={'raw_line': gps_line(speed='1.2garbage')})
    assert batch(client, capture, [bad]).status_code == 400
    assert batch(client, capture, [event()]).status_code == 200
    assert batch(client, capture, [event(seq=1), event(stream='gps')]).status_code == 400


def test_database_sequence_unique_constraint_without_service(client, capture, db):
    from models.models import CollectionInsoleFrame
    from sqlalchemy.exc import IntegrityError
    create(client, capture)
    assert batch(client, capture, [event()]).status_code == 200
    row = CollectionInsoleFrame.query.one()
    values = {c.name: getattr(row, c.name) for c in CollectionInsoleFrame.__table__.columns if c.name != 'id'}
    values['event_id'] = str(uuid4())
    with pytest.raises(IntegrityError):
        db.session.execute(CollectionInsoleFrame.__table__.insert().values(**values))
    db.session.rollback()


def test_file_sqlite_independent_sessions_serialize_concurrent_retries(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from config import create_app, db as database
    file_app = create_app({'SQLALCHEMY_DATABASE_URI':'sqlite:///' + (tmp_path/'collection.db').as_posix(),
                           'SECRET_KEY':'synthetic-thread-test','TESTING':True})
    with file_app.app_context():
        database.create_all()
        with file_app.test_client() as client:
            headers,pid = _setup(client)
            cid = str(uuid4())
            cap = dict(headers=headers,patient_id=pid,capture_id=cid,
                body=dict(capture_id=cid,patient_id=pid,device_code='INSOLE-001',mobile_started_at=stamp()))
            create(client,cap)
    sample = event()
    barrier = Barrier(2)
    def submit(_):
        with file_app.test_client() as client:
            barrier.wait(timeout=10)
            response = batch(client,cap,[sample])
            assert response.status_code == 200
            return response.get_json()['data']['results'][0]['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, range(2))) == ['accepted','duplicate']
    with file_app.app_context():
        assert database.session.query(DeviceRawData).count() == 2
        database.session.remove()
        database.engine.dispose()


def test_semantically_equal_numeric_retry_reuses_receipt(client,capture):
    create(client,capture)
    sample = event()
    sample['payload']['lp1'] = 1
    assert batch(client,capture,[sample]).status_code == 200
    sample['payload']['lp1'] = 1.0
    assert batch(client,capture,[sample]).get_json()['data']['results'][0]['status'] == 'duplicate'
