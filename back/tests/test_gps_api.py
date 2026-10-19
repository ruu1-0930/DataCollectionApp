import json
from pathlib import Path
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from tests.test_collection_ingest import capture, create, batch, event, gps_line, stamp
from tests.test_gps_query import seed_window, gps_get


def test_response_matches_strict_schema(client, capture):
    seed_window(client, capture)
    assert batch(client, capture, [event(stream='gps')]).status_code == 200
    schema = json.loads((Path(__file__).parents[1] / 'contracts/collection_gps_v1.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(gps_get(client, capture))


def test_unauthenticated_and_cross_owner_rejected(client, capture, admin_scope):
    assert client.post('/collection-sessions', json=capture['body']).status_code == 401
    assert client.post('/collection-sessions', json=capture['body'], headers=admin_scope['doctor_b']['headers']).status_code == 403
    assert client.post('/collection-sessions', json=capture['body'], headers=admin_scope['admin']['headers']).status_code == 403
    seed_window(client, capture)
    from models.models import DeviceRawData
    from services.gait_session_revision import _session_id
    sid = _session_id(capture['patient_id'], DeviceRawData.query.first().collected_at)
    path = f"/patients/{capture['patient_id']}/gait/sessions/{sid}/gps"
    assert client.get(path, headers=admin_scope['doctor_b']['headers']).status_code == 403
    assert client.get(path, headers=admin_scope['admin']['headers']).status_code == 200


@pytest.mark.parametrize('query', [{'page':0}, {'page_size':501}, {'extra':1}, {'page':'1.0'}])
def test_pagination_strict(client, capture, query):
    seed_window(client, capture)
    from models.models import DeviceRawData
    from services.gait_session_revision import _session_id
    sid = _session_id(capture['patient_id'], DeviceRawData.query.first().collected_at)
    assert client.get(f"/patients/{capture['patient_id']}/gait/sessions/{sid}/gps", headers=capture['headers'], query_string=query).status_code == 400


def test_body_limits_and_duplicate_keys(client, capture):
    create(client, capture)
    path = '/collection-sessions/' + capture['capture_id'] + '/batches'
    assert client.post(path, headers=capture['headers'], data=' ' * (128*1024+1), content_type='application/json').status_code == 400
    assert client.post(path, headers=capture['headers'], data='{"events":[],"events":[]}', content_type='application/json').status_code == 400
    assert batch(client, capture, [event(seq=i) for i in range(101)]).status_code == 400


def test_gps_insert_does_not_change_published_snapshot(client, capture, db):
    from datetime import datetime, timedelta, timezone
    from models.models import DeviceRawData, AnalysisSnapshot, AgentSnapshotProjection
    from services.gait_session_revision import _session_id
    from services.analysis_snapshot import AnalysisSnapshotService
    seed_window(client, capture)
    rows = DeviceRawData.query.all()
    start = rows[0].collected_at
    sid = _session_id(capture['patient_id'], start)
    actor = rows[0].clinician_id
    now = (start + timedelta(minutes=1) - timedelta(hours=8)).replace(tzinfo=timezone.utc)
    snapshot = AnalysisSnapshotService(clock=lambda: now).ensure_snapshot(actor_id=actor, patient_id=capture['patient_id'], session_id=sid)
    before = [(r.id,r.canonical_payload,r.content_hash,r.state_version) for r in AnalysisSnapshot.query.all()]
    projections = [(r.snapshot_id,r.canonical_payload,r.content_hash) for r in AgentSnapshotProjection.query.all()]
    assert batch(client, capture, [event(stream='gps')]).status_code == 200
    assert gps_get(client, capture)['total'] == 1
    assert [(r.id,r.canonical_payload,r.content_hash,r.state_version) for r in AnalysisSnapshot.query.all()] == before
    assert [(r.snapshot_id,r.canonical_payload,r.content_hash) for r in AgentSnapshotProjection.query.all()] == projections
