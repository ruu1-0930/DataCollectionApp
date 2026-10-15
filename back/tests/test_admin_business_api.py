"""Global business visibility is an explicit, paginated, administrator-only API."""

from uuid import UUID
import pytest


def test_global_lists_and_filters_keep_clinician_visibility_unchanged(client, admin_scope, admin_data):
    headers = admin_scope['admin']['headers']
    response = client.get('/admin/patients', headers=headers)
    assert response.status_code == 200
    assert str(UUID(response.headers['X-Trace-ID'])) == response.headers['X-Trace-ID']
    data = response.get_json()['data']
    assert data['total'] == 2
    assert {item['owner']['id'] for item in data['items']} == {
        admin_scope['doctor_a']['id'], admin_scope['doctor_b']['id']}
    filtered = client.get('/admin/patients', headers=headers,
                          query_string={'hospital': 'synthetic-hospital-1'}).get_json()['data']
    assert filtered['total'] == 1
    assert filtered['items'][0]['id'] == admin_data['other_patient_id']
    own = client.get('/patients', headers=admin_scope['doctor_a']['headers']).get_json()['data']
    assert [item['id'] for item in own] == [admin_data['patient_id']]
    for path in ('/admin/clinicians', '/admin/devices'):
        result = client.get(path, headers=headers)
        assert result.status_code == 200
        assert 'passcode_hash' not in result.get_data(as_text=True)
    patient = client.get(f"/admin/patients/{admin_data['patient_id']}", headers=headers)
    assert patient.status_code == 200
    assert patient.get_json()['data']['phone'] == '13900000000'


def test_raw_pages_do_not_overlap_with_equal_timestamps(client, admin_scope, admin_data):
    headers = admin_scope['admin']['headers']
    path = f"/admin/patients/{admin_data['patient_id']}/raw-data"
    pages = [client.get(path, query_string={'page': p, 'page_size': 2}, headers=headers)
             for p in (1, 2)]
    assert all(response.status_code == 200 for response in pages)
    values = [response.get_json()['data'] for response in pages]
    assert all(value['total'] == 4 for value in values)
    ids = [[item['id'] for item in value['items']] for value in values]
    assert ids[0] + ids[1] == sorted(admin_data['raw_ids'], reverse=True)
    assert values[1]['items'][-1]['transformed']['T1'] == .1


@pytest.mark.parametrize('path', ['/admin/clinicians', '/admin/patients', '/admin/devices',
    '/admin/patients/1', '/admin/patients/1/gait/sessions', '/admin/patients/1/raw-data',
    '/admin/patients/1/gait/snapshots', '/admin/patients/1/gait/snapshots/00000000-0000-4000-8000-000000000001'])
def test_non_admin_is_rejected_before_business_lookup(client, admin_scope, path):
    assert client.get(path, headers=admin_scope['doctor_a']['headers']).status_code == 403
    assert client.get(path).status_code == 401


def test_invalid_queries_and_resource_pairs_are_not_silently_ignored(client, admin_scope, admin_data):
    headers = admin_scope['admin']['headers']
    root = f"/admin/patients/{admin_data['patient_id']}"
    for path in ('/admin/patients?page=0', '/admin/patients?page_size=101',
                 '/admin/patients?role=admin_readonly', '/admin/patients?page=1&page=2',
                 root + '/raw-data?foot=X', root + '/raw-data?start=2026-10-02&end=2026-10-01'):
        assert client.get(path, headers=headers).status_code == 400
    assert client.get(root + f"/raw-data?device_id={admin_data['other_device_id']}", headers=headers).status_code == 404
    assert client.get(f"/admin/patients/{admin_data['other_patient_id']}/gait/snapshots/{admin_data['snapshot_id']}",
                      headers=headers).status_code == 404


def test_saved_snapshot_listing_and_absence_are_explicit(client, admin_scope, admin_data):
    headers = admin_scope['admin']['headers']
    base = f"/admin/patients/{admin_data['patient_id']}/gait"
    sessions = client.get(base + '/sessions', headers=headers)
    assert sessions.status_code == 200
    assert sessions.get_json()['data']['items'][0]['session_id'] == admin_data['session_id']
    snapshots = client.get(base + '/snapshots', headers=headers)
    assert snapshots.status_code == 200
    assert snapshots.get_json()['data']['items'][0]['snapshot_id'] == admin_data['snapshot_id']
    empty = client.get(f"/admin/patients/{admin_data['other_patient_id']}/gait/snapshots", headers=headers)
    assert empty.get_json()['data'] == {'items': [], 'total': 0, 'page': 1, 'page_size': 50}
