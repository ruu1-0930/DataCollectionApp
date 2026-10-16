"""Role boundaries use the database identity and preserve clinician contracts."""

import pytest
from models.models import Clinician, Patient


def test_context_reads_current_database_role(client, db, admin_scope):
    actor = admin_scope['admin']
    response = client.get('/account/context', headers=actor['headers'])
    assert response.status_code == 200
    assert response.get_json()['data'] == {'clinician_id': actor['id'], 'role': 'admin'}
    db.session.get(Clinician, actor['id']).role = 'clinician'
    db.session.commit()
    assert client.get('/account/context', headers=actor['headers']).get_json()['data']['role'] == 'clinician'


def test_context_requires_authentication(client):
    assert client.get('/account/context').status_code == 401


@pytest.mark.parametrize('method,path,body', [
    ('post', '/patients', {'name': 'synthetic', 'phone': '13900000000'}),
    ('post', '/devices', {'device_code': 'synthetic-device'}),
    ('delete', '/devices/1', None),
    ('post', '/devices/synthetic/raw_data', {}),
    ('put', '/clinician/me', {'name': 'changed'}),
])
def test_admin_cannot_use_old_business_writes(client, admin_scope, method, path, body):
    response = getattr(client, method)(path, headers=admin_scope['admin']['headers'], json=body)
    assert response.status_code == 403
    assert Patient.query.count() == 0


@pytest.mark.parametrize('method,path', [
    ('post', '/patients/1/gait/sessions/synthetic/snapshots:ensure'),
    ('get', '/patients/1/gait/snapshots/00000000-0000-4000-8000-000000000001'),
    ('get', '/patients/1/gait/snapshots/00000000-0000-4000-8000-000000000001/status'),
    ('get', '/patients/1/gait/snapshots/00000000-0000-4000-8000-000000000001/agent-projection'),
    ('post', '/patients/1/gait/snapshots/00000000-0000-4000-8000-000000000001/publication-claims'),
])
def test_admin_reaches_snapshot_validation_without_bypassing_missing_resources(client, admin_scope, method, path):
    response = getattr(client, method)(path, headers=admin_scope['admin']['headers'], json={})
    expected = 'invalid_request' if path.endswith('/publication-claims') else 'patient_not_found'
    assert response.status_code == (400 if expected == 'invalid_request' else 404)
    assert response.get_json()['error']['code'] == expected


def test_registration_does_not_allow_role_and_login_profile_is_unchanged(client, admin_scope):
    credentials = admin_scope['doctor_a']['credentials']
    assert client.post('/clinician/enable', json={**credentials, 'role': 'admin'}).status_code == 400
    login = client.post('/clinician/login', json={k: v for k, v in credentials.items() if k != 'dept'})
    assert login.status_code == 200
    assert set(login.get_json()['data']['clinician']) == {'id', 'hospital', 'dept', 'name', 'phone'}
    created = client.post('/patients', headers=admin_scope['doctor_a']['headers'],
                          json={'name': 'synthetic', 'phone': '13900000000'})
    assert created.status_code == 200
