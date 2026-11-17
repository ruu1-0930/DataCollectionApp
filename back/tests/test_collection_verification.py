from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from models.models import CollectionSession, DeviceRawData
from tests.test_collection_ingest import batch, capture, create, event, gps_line, stamp
from tests.test_radar_ingest import radar_event


ZERO = {'insole': 0, 'gps': 0, 'radar': 0}


def v2_body(capture):
    return dict(capture['body'], schema_version=2, registration={
        'schema_version': 1, 'patient_id': capture['patient_id'],
        'patient_snapshot': {'name': '合成患者', 'gender': '男', 'age': 60, 'height_cm': 170,
                             'weight_kg': 65, 'shoe_size_eu': 40.5},
        'test_type': 'static_standing', 'remarks': '合成备注',
    })


def create_v2(client, capture, body=None):
    return client.post('/v2/collection-sessions', headers=capture['headers'],
                       json=v2_body(capture) if body is None else body)


def stop_v2(client, capture, counts, *, version=2):
    return client.post(f"/v2/collection-sessions/{capture['capture_id']}/stop", headers=capture['headers'],
                       json={'schema_version': version, 'mobile_stopped_at': stamp(5000), 'final_counts': counts})


def receipt(response):
    assert response.status_code == 200, response.get_json()
    data = response.get_json()['data']
    assert set(data) == {'capture_id', 'verification'}
    verification = data['verification']
    assert verification['record_id'] == data['capture_id']
    contract = json.loads((Path(__file__).parents[1] / 'contracts/collection_v2.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator(dict(contract, **{'$ref': '#/$defs/CollectionVerificationV1'})).validate(verification)
    return verification


def test_final_counts_count_distinct_frame_nofix_gps_and_radar_rows(client, capture):
    assert create_v2(client, capture).status_code == 200
    samples = [event(), event(stream='gps', payload={'raw_line': gps_line(
        fix='0', lat='nan', lon='nan', alt='nan', speed='nan', hdop='nan')}), radar_event()]
    for sample in samples:
        assert batch(client, capture, [sample]).get_json()['data']['results'][0]['status'] == 'accepted'
        assert batch(client, capture, [sample]).get_json()['data']['results'][0]['status'] == 'duplicate'
    counts = {'insole': 1, 'gps': 1, 'radar': 1}
    first = receipt(stop_v2(client, capture, counts))
    assert first['expected_counts'] == first['received_counts'] == counts
    assert first['upload_state'] == 'verified'
    assert DeviceRawData.query.count() == 2
    for sample in samples:
        assert batch(client, capture, [sample]).get_json()['data']['results'][0]['status'] == 'duplicate'
    assert batch(client, capture, [event(seq=1)]).status_code == 409
    assert receipt(stop_v2(client, capture, counts)) == first


def test_mismatch_keeps_first_declaration_and_freezes_new_events(client, capture):
    assert create_v2(client, capture).status_code == 200
    assert batch(client, capture, [event()]).status_code == 200
    counts = {'insole': 0, 'gps': 1, 'radar': 0}
    first = receipt(stop_v2(client, capture, counts))
    assert first['upload_state'] == 'mismatch'
    assert first['expected_counts'] == counts
    assert first['received_counts'] == {'insole': 1, 'gps': 0, 'radar': 0}
    assert stop_v2(client, capture, first['received_counts']).status_code == 409
    assert batch(client, capture, [event(stream='gps')]).status_code == 409
    assert receipt(stop_v2(client, capture, counts)) == first


def test_zero_event_stop_can_be_verified(client, capture):
    assert create_v2(client, capture).status_code == 200
    result = receipt(stop_v2(client, capture, ZERO))
    assert result['expected_counts'] == result['received_counts'] == ZERO
    assert result['upload_state'] == 'verified'


def test_registration_snapshot_has_canonical_hash_and_immutable_identity(client, capture, db):
    source = v2_body(capture)
    source['registration']['remarks'] = 'Cafe\u0301'
    assert create_v2(client, capture, source).status_code == 200
    equivalent = deepcopy(source)
    equivalent['registration']['patient_snapshot']['height_cm'] = 170.0
    equivalent['registration']['remarks'] = 'Café'
    assert create_v2(client, capture, equivalent).status_code == 200
    assert client.put(f"/v2/patients/{capture['patient_id']}/profile", headers=capture['headers'],
                      json=dict(equivalent['registration']['patient_snapshot'], name='新名称')).status_code == 200
    changed = deepcopy(equivalent)
    changed['registration']['remarks'] = '新备注'
    assert create_v2(client, capture, changed).status_code == 409
    row = db.session.get(CollectionSession, capture['capture_id'])
    assert row.registration_hash == sha256(row.registration_json.encode('utf-8')).hexdigest()
    assert json.loads(row.registration_json) == equivalent['registration']
    assert row.metadata_schema_version == 1 and row.test_type == 'static_standing'


@pytest.mark.parametrize('change', [
    lambda p: p.update(schema_version=2.0),
    lambda p: p['registration'].update(patient_id=p['patient_id'] + 1),
    lambda p: p['registration'].update(schema_version=True),
    lambda p: p['registration'].update(remarks=None),
    lambda p: p['registration'].update(test_type='legacy_unspecified'),
    lambda p: p['registration']['patient_snapshot'].update(phone=None),
    lambda p: p['registration']['patient_snapshot'].update(age=60.0),
    lambda p: p['registration']['patient_snapshot'].update(shoe_size_eu=40.25),
])
def test_registration_shape_and_identity_are_strict(client, capture, change):
    body = v2_body(capture)
    change(body)
    assert create_v2(client, capture, body).status_code == 400
    assert CollectionSession.query.count() == 0


@pytest.mark.parametrize('counts', [dict(ZERO, gps=True), dict(ZERO, gps=0.0), dict(ZERO, gps=-1),
                                    dict(ZERO, gps=9007199254740992), dict(ZERO, extra=0), {'gps': 0, 'insole': 0}])
def test_final_counts_are_exact_nonnegative_safe_integers(client, capture, counts):
    assert create_v2(client, capture).status_code == 200
    assert stop_v2(client, capture, counts).status_code == 400
    assert receipt(stop_v2(client, capture, ZERO))['upload_state'] == 'verified'


def test_routes_keep_legacy_and_registered_stop_protocols_separate(client, capture):
    from access import load_account_context
    from services.collection_verification import verify_capture

    path = f"/collection-sessions/{capture['capture_id']}/stop"
    assert client.post('/collection-sessions', headers=capture['headers'], json=v2_body(capture)).status_code == 400
    assert create_v2(client, capture, capture['body']).status_code == 400
    create(client, capture)
    assert create_v2(client, capture).status_code == 409
    assert stop_v2(client, capture, ZERO).status_code == 409
    assert client.post(path, headers=capture['headers'], json={'mobile_stopped_at': stamp(5000)}).get_json()['data'] == {'capture_id': capture['capture_id']}
    actor = load_account_context(CollectionSession.query.one().clinician_id)
    first = verify_capture(actor, capture['capture_id'])
    assert first['upload_state'] == 'unknown' and first['expected_counts'] is None
    assert first['received_counts'] == ZERO
    assert batch(client, capture, [event()]).status_code == 200
    later = verify_capture(actor, capture['capture_id'])
    assert later['received_counts'] == dict(ZERO, insole=1)
    assert later['record_version'] != first['record_version']
    assert later['upload_state'] == 'unknown'
