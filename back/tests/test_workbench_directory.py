"""The shared directory exposes scope, not a second patient database."""

from uuid import UUID

import pytest
from models.models import PatientPII


def test_shared_directory_keeps_doctor_scope_and_returns_admin_owners(client, admin_scope, admin_data):
    response = client.get('/workbench/patients', headers=admin_scope['admin']['headers'])
    assert response.status_code == 200
    assert str(UUID(response.headers['X-Trace-ID'])) == response.headers['X-Trace-ID']
    data = response.get_json()['data']
    assert data['total'] == 2 and data['page'] == 1 and data['page_size'] == 50
    assert [row['id'] for row in data['items']] == [admin_data['other_patient_id'], admin_data['patient_id']]
    assert {row['owner']['id'] for row in data['items']} == {
        admin_scope['doctor_a']['id'], admin_scope['doctor_b']['id']}
    assert all(set(row['owner']) == {'id', 'hospital', 'dept', 'name'} for row in data['items'])
    assert all(set(row) == {'id', 'subject_id', 'name', 'gender', 'age', 'last_collected_at', 'owner'}
               for row in data['items'])
    own = client.get('/workbench/patients', headers=admin_scope['doctor_a']['headers'])
    assert own.status_code == 200
    assert [row['id'] for row in own.get_json()['data']['items']] == [admin_data['patient_id']]


def test_directory_filters_paginate_and_never_elevate_doctor(client, admin_scope, admin_data):
    h = admin_scope['admin']['headers']
    page = client.get('/workbench/patients?page=2&page_size=1', headers=h)
    assert page.status_code == 200
    assert page.get_json()['data']['total'] == 2
    assert page.get_json()['data']['items'][0]['id'] == admin_data['patient_id']
    filtered = client.get('/workbench/patients', headers=h, query_string={
        'hospital': 'synthetic-hospital-1', 'clinician_id': admin_scope['doctor_b']['id']})
    assert filtered.status_code == 200
    assert [row['id'] for row in filtered.get_json()['data']['items']] == [admin_data['other_patient_id']]
    foreign = client.get('/workbench/patients', headers=admin_scope['doctor_a']['headers'],
                         query_string={'clinician_id': admin_scope['doctor_b']['id']})
    assert foreign.status_code == 403
    empty = client.get('/workbench/patients?page=9', headers=h).get_json()['data']
    assert empty == {'items': [], 'total': 2, 'page': 9, 'page_size': 50}


def test_search_treats_wildcards_literally_and_preserves_missing_name(client, db, admin_scope, admin_data):
    pii = db.session.query(PatientPII).filter_by(patient_id=admin_data['patient_id']).one()
    pii.name = 'synthetic%_patient'
    other = db.session.query(PatientPII).filter_by(patient_id=admin_data['other_patient_id']).one()
    # PII rows may be absent; name itself is NOT NULL when a row exists.
    db.session.delete(other)
    db.session.commit()
    h = admin_scope['admin']['headers']
    response = client.get('/workbench/patients', headers=h, query_string={'q': ' %_ '})
    assert response.status_code == 200
    assert [row['id'] for row in response.get_json()['data']['items']] == [admin_data['patient_id']]
    by_number = client.get('/workbench/patients', headers=h, query_string={'q': '#admin-1'})
    assert by_number.status_code == 200
    assert by_number.get_json()['data']['items'][0]['name'] is None


def test_doctor_picker_is_admin_only_minimal_and_searchable(client, admin_scope):
    h = admin_scope['admin']['headers']
    response = client.get('/workbench/clinicians?q=doctor&page_size=1&page=2', headers=h)
    assert response.status_code == 200
    assert response.get_json()['data']['total'] == 2
    rows = response.get_json()['data']['items']
    assert rows == [{'id': admin_scope['doctor_b']['id'], 'hospital': 'synthetic-hospital-1',
                     'dept': 'synthetic', 'name': 'synthetic-doctor_b'}]
    assert client.get('/workbench/clinicians', headers=admin_scope['doctor_a']['headers']).status_code == 403


@pytest.mark.parametrize('query', ['page=0', 'page_size=101', 'clinician_id=-1', 'page=1&page=2',
                                  'role=admin', 'q=' + 'x' * 101, 'page=true'])
def test_bad_directory_query_is_not_silently_ignored(client, admin_scope, query):
    response = client.get('/workbench/patients?' + query, headers=admin_scope['admin']['headers'])
    assert response.status_code == 400
    assert response.get_json()['code'] == 400


@pytest.mark.parametrize('path', ['/workbench/patients', '/workbench/clinicians'])
def test_directory_requires_current_account(client, path):
    assert client.get(path).status_code == 401
