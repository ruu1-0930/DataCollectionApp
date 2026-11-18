import json

from models.models import CollectionInsoleFrame, CollectionSession, GaitSessionRevision
from tests.test_collection_ingest import batch, capture, event, stamp
from tests.test_collection_records import other_capture
from tests.test_collection_verification import create_v2, stop_v2, v2_body


def test_capture_snapshot_ignores_neighbor_task_and_uses_stop_receipt(client, capture):
    neighbor = other_capture(capture, 0)
    for cap, task in ((capture, 'walk_10m_usual'), (neighbor, 'tug')):
        body = v2_body(cap)
        body['registration']['test_type'] = task
        assert create_v2(client, cap, body).status_code == 200
        assert batch(client, cap, [event(ms=1000)]).status_code == 200
    counts = {'insole': 1, 'gps': 0, 'radar': 0}
    assert stop_v2(client, capture, counts).status_code == 200
    cap_id, patient = capture['capture_id'], capture['patient_id']
    path = f'/v3/patients/{patient}/collections/{cap_id}/snapshots:ensure'
    headers = capture['headers']
    response = client.post(path, headers=headers)
    assert response.status_code == 201, response.get_json()
    full = response.get_json()
    assert client.post(path, headers=headers).get_json() == full
    sid = full['snapshot_id']
    base = f'/patients/{patient}/gait/snapshots/{sid}'
    assert client.get(base, headers=headers).get_json() == full
    assert client.get(base + '/status', headers=headers).get_json()['state'] == 'published'
    projection = client.get(base + '/agent-projection', headers=headers).get_json()
    assert projection['snapshot_content_hash'] == full['content_hash']
    registered = CollectionSession.query.filter_by(capture_id=cap_id).one()
    assert projection['source'] == full['source'] == {
        'kind': 'capture', 'capture_id': cap_id, 'registration_hash': registered.registration_hash,
        'test_type': 'walk_10m_usual'}
    assert projection['session_id'] == full['session_id'] == 'C:' + cap_id
    closure = full['session']['closure']
    assert set(closure) == {'policy_version', 'reason', 'stop_received_at', 'final_counts', 'registration_hash'}
    assert closure['final_counts'] == counts and closure['registration_hash'] == registered.registration_hash
    assert (closure['policy_version'], closure['reason']) == ('capture-v1', 'capture_stop_receipt')
    frame = CollectionInsoleFrame.query.filter_by(capture_id=cap_id).one()
    revision = GaitSessionRevision.query.filter_by(id=full['session_revision_id']).one()
    assert json.loads(revision.ordered_row_ids_canonical) == [frame.left_raw_id, frame.right_raw_id]
    assert full['session']['row_count'] == 2
    assert client.post(path.replace(cap_id, neighbor['capture_id']), headers=headers).status_code == 409
    assert client.post(f'/patients/{patient}/gait/sessions/C:{cap_id}/snapshots:ensure',
                       headers=headers).status_code == 400


def test_capture_long_pause_does_not_split_task_and_nonwalk_has_no_gait_flags(client, capture):
    assert create_v2(client, capture).status_code == 200
    assert batch(client, capture, [event(seq=0, ms=0), event(seq=1, ms=45000)]).status_code == 200
    cap_id, patient, headers = capture['capture_id'], capture['patient_id'], capture['headers']
    assert client.post(f'/v2/collection-sessions/{cap_id}/stop', headers=headers, json={
        'schema_version': 2, 'mobile_stopped_at': stamp(45000),
        'final_counts': {'insole': 2, 'gps': 0, 'radar': 0}}).status_code == 200
    response = client.post(f'/v3/patients/{patient}/collections/{cap_id}/snapshots:ensure', headers=headers)
    assert response.status_code == 201, response.get_json()
    full = response.get_json()
    assert full['flags'] == [] and full['data_quality']['total_frames'] == 2
    assert full['source']['test_type'] == 'static_standing'


def test_empty_stopped_and_mismatched_capture_do_not_publish(client, capture):
    for cap, expected in ((capture, 0), (other_capture(capture, 0), 2)):
        assert create_v2(client, cap).status_code == 200
        assert stop_v2(client, cap, {'insole': expected, 'gps': 0, 'radar': 0}).status_code == 200
        path = f"/v3/patients/{cap['patient_id']}/collections/{cap['capture_id']}/snapshots:ensure"
        assert client.post(path, headers=cap['headers']).status_code == 422
    assert GaitSessionRevision.query.count() == 0
