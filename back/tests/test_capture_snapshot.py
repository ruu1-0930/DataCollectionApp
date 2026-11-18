from datetime import datetime
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import event as sql_event
from sqlalchemy.orm import Session

from models.models import AnalysisSnapshot, CollectionInsoleFrame, CollectionSession, DeviceRawData, GaitSessionRevision, Patient
from services.gait_session_revision import _session_id
from services.collection_verification import verify_capture
from tests.test_collection_ingest import batch, capture, event, stamp
from tests.test_collection_records import _legacy_left, other_capture
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
    assert (full['session']['start_at'], full['session']['end_at']) == (stamp(0), stamp(45000))
    assert [point['t_ms'] for point in full['chart_series']] == [0, 45000]


def test_empty_stopped_and_mismatched_capture_do_not_publish(client, capture):
    for cap, expected in ((capture, 0), (other_capture(capture, 0), 2)):
        assert create_v2(client, cap).status_code == 200
        assert stop_v2(client, cap, {'insole': expected, 'gps': 0, 'radar': 0}).status_code == 200
        path = f"/v3/patients/{cap['patient_id']}/collections/{cap['capture_id']}/snapshots:ensure"
        assert client.post(path, headers=cap['headers']).status_code == 422
    assert GaitSessionRevision.query.count() == 0


@pytest.mark.parametrize('mixed', [False, True])
def test_registered_members_block_legacy_time_key_and_preserve_historical_bytes(client, capture, db, monkeypatch, mixed):
    clock = datetime(2020, 1, 1)
    monkeypatch.setattr('services.collection_ingest.server_now', lambda: clock)
    assert create_v2(client, capture).status_code == 200
    assert batch(client, capture, [event()]).status_code == 200
    registered = CollectionSession.query.one()
    raw_at = DeviceRawData.query.first().collected_at
    if mixed:
        _legacy_left(db, registered, raw_at)
    # Seed an already published legacy artifact before revealing its capture membership.
    registered.metadata_schema_version = None
    db.session.commit()
    headers, patient = capture['headers'], capture['patient_id']
    legacy_path = f'/patients/{patient}/gait/sessions/{_session_id(patient, raw_at)}/snapshots:ensure'
    old = client.post(legacy_path, headers=headers)
    assert old.status_code == 201
    historical = AnalysisSnapshot.query.one().canonical_payload
    registered.metadata_schema_version = 1
    db.session.commit()
    response = client.post(legacy_path, headers=headers)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()['error']['code'] == 'scope_mismatch'
    assert 'capture' in response.get_json()['error']['message']
    path = f"/patients/{patient}/gait/snapshots/{old.get_json()['snapshot_id']}"
    assert client.get(path, headers=headers).get_json() == old.get_json()
    assert client.get(path+'/status', headers=headers).get_json()['state'] == 'published'
    assert AnalysisSnapshot.query.one().canonical_payload == historical


def test_capture_upload_and_ensure_acquire_patient_before_capture(client, capture):
    assert create_v2(client, capture).status_code == 200
    locks = []
    def record(state):
        stmt = state.statement
        if getattr(stmt, '_for_update_arg', None) is not None:
            locks.extend(column.get('entity') for column in stmt.column_descriptions)
    sql_event.listen(Session, 'do_orm_execute', record)
    try:
        assert batch(client, capture, [event()]).status_code == 200
        assert locks[:2] == [Patient, CollectionSession], locks
        locks.clear()
        path = f"/v3/patients/{capture['patient_id']}/collections/{capture['capture_id']}/snapshots:ensure"
        assert client.post(path, headers=capture['headers']).status_code == 409
        assert locks[:2] == [Patient, CollectionSession], locks
        locks.clear()
        assert stop_v2(client, capture, {'insole':1, 'gps':0, 'radar':0}).status_code == 200
        assert locks[:2] == [Patient, CollectionSession], locks
        actor = SimpleNamespace(clinician_id=CollectionSession.query.one().clinician_id)
        locks.clear()
        assert verify_capture(actor, capture['capture_id'])['upload_state'] == 'verified'
        assert locks[:2] == [Patient, CollectionSession], locks
    finally:
        sql_event.remove(Session, 'do_orm_execute', record)


def test_capture_event_bounds_and_chart_use_mobile_clock_for_reordered_upload(client, capture, monkeypatch):
    monkeypatch.setattr('services.collection_ingest.server_now', lambda: datetime(2025, 1, 1))
    assert create_v2(client, capture).status_code == 200
    late, early = event(seq=1, ms=45000), event(seq=0, ms=0)
    assert batch(client, capture, [late, early]).status_code == 200
    cap_id, headers = capture['capture_id'], capture['headers']
    assert client.post(f'/v2/collection-sessions/{cap_id}/stop', headers=headers, json={
        'schema_version':2,'mobile_stopped_at':stamp(45000),'final_counts':{'insole':2,'gps':0,'radar':0}}).status_code == 200
    result = client.post(f"/v3/patients/{capture['patient_id']}/collections/{cap_id}/snapshots:ensure", headers=headers)
    assert result.status_code == 201
    full = result.get_json()
    assert (full['session']['start_at'], full['session']['end_at']) == (stamp(0), stamp(45000))
    assert [point['t_ms'] for point in full['chart_series']] == [0, 45000]
    assert {r.uploaded_at for r in DeviceRawData.query.all()} == {datetime(2025,1,1,8)}
