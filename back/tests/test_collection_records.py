from datetime import datetime, timedelta
from functools import lru_cache
import json
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
import pytest
from referencing import Registry, Resource

from models.models import AnalysisSnapshot, DeviceRawData
from services.collection_ingest import LEFT_FIELDS
from services.gait_session_revision import _session_id
from tests.test_collection_ingest import batch, capture, create, event, stamp
from tests.test_collection_verification import create_v2, stop_v2, v2_body
from tests.test_radar_ingest import radar_event
from tests.test_raw_data import _frame


@lru_cache(maxsize=None)
def contract(definition):
    root = Path(__file__).parents[1] / 'contracts'
    base = 'https://contracts.sarcogait.test/'
    names = ('collection_records_v1', 'collection_registration_v1', 'collection_v2', 'collection_radar_v1')
    registry = Registry()
    for name in names:
        filename = f'{name}.schema.json'
        document = json.loads((root / filename).read_text(encoding='utf-8'))
        Draft202012Validator.check_schema(document)
        registry = registry.with_resource(base + filename, Resource.from_contents(document))
    return Draft202012Validator({'$ref': base + f'collection_records_v1.schema.json#/$defs/{definition}'},
                                 registry=registry, format_checker=FormatChecker())


def collection_path(cap, suffix=''):
    return f"/v2/patients/{cap['patient_id']}/collections{suffix}"


def read(client, cap, suffix='', **args):
    response = client.get(collection_path(cap, suffix), headers=cap['headers'], query_string=args)
    assert response.status_code == 200, response.get_json()
    return response.get_json()['data']


def other_capture(cap, start_ms):
    capture_id = str(uuid4())
    return dict(cap, capture_id=capture_id,
                body=dict(cap['body'], capture_id=capture_id, mobile_started_at=stamp(start_ms)))


def test_back_to_back_tasks_and_empty_capture_are_separate_records(client, capture):
    second = other_capture(capture, 0)
    empty = other_capture(capture, 1000)
    gps_only = other_capture(capture, 1000)
    radar_only = other_capture(capture, 1000)
    for cap, test_type in zip((capture, second, empty, gps_only, radar_only),
                              ('static_standing', 'tug', 'free_capture', 'walk_10m_usual', 'five_times_sit_to_stand')):
        body = v2_body(cap)
        body['registration']['test_type'] = test_type
        assert create_v2(client, cap, body).status_code == 200

    first_frame = event(ms=1000)
    other_frame = event(ms=1000)
    assert batch(client, capture, [first_frame]).status_code == 200
    assert batch(client, second, [other_frame]).status_code == 200
    assert batch(client, gps_only, [event(ms=1000, stream='gps')]).status_code == 200
    assert batch(client, radar_only, [radar_event(ms=1000)]).status_code == 200

    directory = read(client, capture)
    contract('CollectionPageV1').validate(directory)
    records = {record['record_id']: record for record in directory['items']}
    assert {key: tuple(record['received_counts'][stream] for stream in ('insole', 'gps', 'radar'))
            for key, record in records.items()} == {
        capture['capture_id']: (1, 0, 0), second['capture_id']: (1, 0, 0),
        empty['capture_id']: (0, 0, 0), gps_only['capture_id']: (0, 1, 0), radar_only['capture_id']: (0, 0, 1),
    }
    for cap, sample in ((capture, first_frame), (second, other_frame)):
        frames = read(client, cap, f"/{cap['capture_id']}/frames")['items']
        assert [frame['event_id'] for frame in frames] == [sample['event_id']]
        assert len({frames[0]['left']['raw_id'], frames[0]['right']['raw_id']}) == 2


def test_all_501_frames_have_stable_cursors_and_verification_without_snapshot(client, capture):
    assert create_v2(client, capture).status_code == 200
    samples = [event(seq=0, ms=5000), event(seq=2, ms=0)]
    samples += [event(seq=seq, ms=1000) for seq in range(3, 502)]
    for start in range(0, len(samples), 100):
        response = batch(client, capture, samples[start:start + 100])
        assert response.status_code == 200, response.get_json()

    counts = {'insole': 501, 'gps': 0, 'radar': 0}
    stopped = stop_v2(client, capture, counts)
    assert stopped.status_code == 200, stopped.get_json()
    path = '/' + capture['capture_id']
    first = read(client, capture, path + '/frames')
    second = read(client, capture, path + '/frames', cursor=first['next_cursor'])
    for page in (first, second):
        contract('FramePage').validate(page)
    assert len(first['items']) == 500 and len(second['items']) == 1
    assert second['next_cursor'] is None
    items = first['items'] + second['items']
    assert [frame['event_id'] for frame in items] == [sample['event_id'] for sample in samples]
    assert [frame['mobile_received_at'] for frame in items[:2]] == [stamp(5000), stamp(0)]
    assert len({frame['left']['raw_id'] for frame in items} | {frame['right']['raw_id'] for frame in items}) == 1002
    assert items[0]['left']['pressure'] == {f'p{i}': i for i in range(1, 10)}
    assert items[0]['right']['imu']['gz'] == 115
    assert items[0]['left']['walking_speed_mps'] == 1.1

    detail = read(client, capture, path)
    verification = read(client, capture, path + '/verification')
    contract('CollectionRecordV1').validate(detail)
    contract('CollectionVerificationV1').validate(verification)
    assert verification['expected_counts'] == verification['received_counts'] == counts
    assert verification['upload_state'] == 'verified' and detail['capture_state'] == 'stopped'
    assert verification['record_version'] == detail['record_version'] == first['record_version'] == second['record_version']
    assert verification['record_version'] == stopped.get_json()['data']['verification']['record_version']
    assert detail['duration_s'] == 5 and detail['recorded_through_at'] is not None
    assert detail['technical_quality'] == {
        'left_raw_rows': 501, 'right_raw_rows': 501, 'frames_missing_left': 0, 'frames_missing_right': 0,
        'missing_required_values': 0, 'mobile_time_regressions': 1, 'insole_sequence_gaps': 1,
    }
    assert AnalysisSnapshot.query.count() == 0
    with pytest.raises(ValidationError):
        contract('FramePage').validate(dict(second, items=[dict(items[0], surprise='forbidden')]))


def test_sidecar_pages_follow_only_capture_and_keep_unmatched_edges(client, capture):
    neighbor = other_capture(capture, 0)
    for cap in (capture, neighbor):
        create(client, cap)
        assert batch(client, cap, [event(ms=2500)]).status_code == 200
    nofix = 'GPS1,5,0,nan,nan,nan,nan,0,99.99,617,,16607,0'
    gps = [event(stream='gps', ms=0, payload={'raw_line': nofix}), event(stream='gps', ms=5000, seq=1)]
    radar = [radar_event(ms=0, age_ms=9007199254740993), radar_event(ms=5000, seq=1)]
    for stream, samples, definition in (('gps', gps, 'GpsPage'), ('radar', radar, 'RadarPage')):
        assert batch(client, capture, samples).status_code == 200
        assert batch(client, neighbor, [dict(samples[0], event_id=str(uuid4()))]).status_code == 200
        path = f"/{capture['capture_id']}/{stream}"
        first = read(client, capture, path, limit=1)
        last = read(client, capture, path, cursor=first['next_cursor'], limit=1)
        contract(definition).validate(first)
        contract(definition).validate(last)
        items = first['items'] + last['items']
        assert [item['event_id'] for item in items] == [sample['event_id'] for sample in samples]
        assert [item['mobile_received_at'] for item in items] == [stamp(0), stamp(5000)]
        assert all(item['capture_id'] == capture['capture_id'] for item in items)
        assert last['next_cursor'] is None
        if stream == 'gps':
            assert items[0]['raw_line'] == nofix and items[0]['lat'] is None
            assert items[0]['quality'] == 'invalid' and 'no_fix' in items[0]['reason_codes']
        else:
            assert items[0]['payload'] == samples[0]['payload']
        invalid = client.get(collection_path(neighbor, f"/{neighbor['capture_id']}/{stream}"),
                             headers=neighbor['headers'], query_string={'cursor': first['next_cursor']})
        assert invalid.status_code == 400
    detail = read(client, capture, f"/{capture['capture_id']}")
    assert detail['test_type'] == 'legacy_unspecified' and detail['patient_snapshot'] is None
    assert read(client, capture, f"/{capture['capture_id']}/verification")['upload_state'] == 'unknown'


def test_directory_cursor_and_filters_use_current_profile_and_local_capture_day(client, capture):
    before_midnight = other_capture(capture, 16 * 3600000 - 1)
    midnight = other_capture(capture, 16 * 3600000)
    tied = other_capture(capture, 16 * 3600000)
    records = [
        (before_midnight, 60, 'static_standing'), (midnight, 61, 'tug'), (tied, 61, 'tug'),
    ]
    for cap, age, test_type in records:
        body = v2_body(cap)
        body['registration']['test_type'] = test_type
        body['registration']['patient_snapshot']['age'] = age
        assert create_v2(client, cap, body).status_code == 200
    current = dict(v2_body(capture)['registration']['patient_snapshot'], name='Current Synthetic', age=75)
    assert client.put(f"/v2/patients/{capture['patient_id']}/profile",
                      headers=capture['headers'], json=current).status_code == 200
    criteria = dict(patient_name='  CURRENT ', current_age_min=75, current_age_max=75, age_at_capture_min=61,
                    age_at_capture_max=61, test_type='tug', date_from='2026-10-20', date_to='2026-10-20',
                    capture_state='active', upload_state='pending')
    one = read(client, capture, limit=1, **criteria)
    two = read(client, capture, cursor=one['next_cursor'], limit=1, **criteria)
    assert [item['record_id'] for item in one['items'] + two['items']] == sorted(
        [midnight['capture_id'], tied['capture_id']], reverse=True)
    assert two['next_cursor'] is None
    assert one['items'][0]['patient_snapshot']['age'] == 61
    assert read(client, capture, date_to='2026-10-19')['items'][0]['record_id'] == before_midnight['capture_id']
    assert read(client, capture, current_age_max=74)['items'] == []
    assert read(client, capture, age_at_capture_min=75)['items'] == []
    for query in ({'cursor': one['next_cursor']}, {'age_at_capture_min': 151}, {'limit': 0},
                  {'test_type': 'walk'}, {'date_to': '2026-02-30'}, {'extra': 1},
                  [('limit', '1'), ('limit', '2')]):
        assert client.get(collection_path(capture), headers=capture['headers'], query_string=query).status_code == 400


def _legacy_left(db, source, at, **overrides):
    values = {target: _frame()[key] for target, key in LEFT_FIELDS.items()}
    values.update(overrides)
    row = DeviceRawData(device_id=source.device_id, patient_id=source.patient_id, clinician_id=source.clinician_id,
                        foot='L', collected_at=at, uploaded_at=at, **values)
    db.session.add(row)
    db.session.flush()
    return row.id


def test_legacy_identity_spans_original_gap_but_uses_only_unclaimed_sources(client, capture, db, monkeypatch):
    owner_utc = datetime(2026, 10, 20, 15, 59, 50, 123000)
    monkeypatch.setattr('services.collection_ingest.server_now', lambda: owner_utc)
    create(client, capture)
    assert batch(client, capture, [event()]).status_code == 200
    captured = DeviceRawData.query.filter_by(foot='L').one()
    old_start = datetime(2026, 10, 20, 23, 59, 50, 123000)
    timestamp = old_start + timedelta(seconds=10)
    only_left_id = _legacy_left(db, captured, timestamp, walking_speed=float('inf'))
    second_id = _legacy_left(db, captured, timestamp + timedelta(seconds=30))
    pure_time = timestamp + timedelta(seconds=60, microseconds=1)
    pure_id = _legacy_left(db, captured, pure_time)
    db.session.commit()

    sid = _session_id(capture['patient_id'], old_start)
    pure_sid = _session_id(capture['patient_id'], pure_time)
    results = {item['record_id']: item for item in read(client, capture)['items']}
    assert set(results) == {sid, pure_sid, capture['capture_id']}
    mixed = read(client, capture, '/' + sid)
    contract('CollectionRecordV1').validate(mixed)
    assert mixed['record_id'] == sid and mixed['record_kind'] == 'legacy_session'
    assert mixed['started_at'] == '2026-10-20T16:00:00.123000Z'
    assert mixed['duration_s'] == 30 and mixed['patient_snapshot'] is None
    assert mixed['technical_quality'] == {
        'left_raw_rows': 2, 'right_raw_rows': 0, 'frames_missing_left': 0, 'frames_missing_right': 2,
        'missing_required_values': 9, 'mobile_time_regressions': None, 'insole_sequence_gaps': None,
    }
    assert results[sid]['record_version'] == mixed['record_version']
    first = read(client, capture, '/' + sid + '/frames', limit=1)
    last = read(client, capture, '/' + sid + '/frames', limit=1, cursor=first['next_cursor'])
    assert first['record_version'] == last['record_version'] == mixed['record_version']
    assert first['items'][0]['left']['walking_speed_mps'] is None
    assert [frame['left']['raw_id'] for frame in first['items'] + last['items']] == [only_left_id, second_id]
    assert all(frame['right'] is None for frame in first['items'] + last['items'])
    assert read(client, capture, '/' + pure_sid + '/frames')['items'][0]['left']['raw_id'] == pure_id
    for stream in ('gps', 'radar'):
        assert read(client, capture, '/' + sid + '/' + stream)['items'] == []
    legacy_verification = read(client, capture, '/' + sid + '/verification')
    contract('CollectionVerificationV1').validate(legacy_verification)
    assert legacy_verification['expected_counts'] is None and legacy_verification['upload_state'] == 'unknown'
    assert legacy_verification['received_counts'] == {'insole': 2, 'gps': 0, 'radar': 0}
    assert legacy_verification['record_version'] == mixed['record_version']
    assert {item['record_id'] for item in read(client, capture, date_from='2026-10-21')['items']} == {sid, pure_sid}

    _legacy_left(db, captured, timestamp)
    db.session.commit()
    changed = read(client, capture, '/' + sid)
    assert changed['record_version'] != mixed['record_version']
    assert changed['received_counts']['insole'] == 3


def test_patient_and_record_ownership_are_rechecked_for_all_raw_routes(client, capture, admin_scope):
    create(client, capture)
    cap_id = capture['capture_id']
    unrelated = client.post('/v2/patients', headers=capture['headers'],
                            json=dict(v2_body(capture)['registration']['patient_snapshot'], name='Other'))
    assert unrelated.status_code == 200, unrelated.get_json()
    wrong_patient = dict(capture, patient_id=unrelated.get_json()['data']['id'])
    outsider = admin_scope['doctor_b']['headers']
    for suffix in ('', '/verification', '/frames', '/gps', '/radar'):
        path = '/' + cap_id + suffix
        assert client.get(collection_path(capture, path), headers=outsider).status_code == 403
        assert client.get(collection_path(wrong_patient, path), headers=capture['headers']).status_code == 404
        assert client.get(collection_path(capture, path), headers=admin_scope['admin']['headers']).status_code == 200
    assert client.get(collection_path(capture), headers=outsider).status_code == 403
