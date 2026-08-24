def _auth(client):
    token = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr', 'phone': '13800000000',
        'passcode': '1234'}).get_json()['data']['token']
    return {'Authorization': f'Bearer {token}'}


def test_register_device_via_bluetooth(client):
    resp = client.post('/devices', headers=_auth(client),
                       json={'device_code': 'INSOLE-001', 'device_name': '左脚鞋垫'})
    data = resp.get_json()['data']
    assert data['device_code'] == 'INSOLE-001'
    assert data['is_enabled'] is True


def test_register_device_requires_code(client):
    resp = client.post('/devices', headers=_auth(client), json={'device_name': 'x'})
    assert resp.get_json()['code'] == 400


def test_list_and_delete_device(client):
    auth = _auth(client)
    did = client.post('/devices', headers=auth,
                      json={'device_code': 'INSOLE-001'}).get_json()['data']['id']
    assert len(client.get('/devices', headers=auth).get_json()['data']) == 1
    assert client.delete(f'/devices/{did}', headers=auth).get_json()['code'] == 200
    assert len(client.get('/devices', headers=auth).get_json()['data']) == 0


def test_device_code_cannot_be_rebound_to_another_clinician(client):
    first_auth = _auth(client)
    original = client.post(
        '/devices',
        headers=first_auth,
        json={'device_code': 'INSOLE-001', 'device_name': '原始名称'},
    )
    assert original.status_code == 200

    same_owner = client.post(
        '/devices',
        headers=first_auth,
        json={'device_code': 'INSOLE-001', 'device_name': '不应改名'},
    )
    assert same_owner.status_code == 200
    assert same_owner.get_json()['data'] == original.get_json()['data']

    second_token = client.post('/clinician/enable', json={
        'hospital': 'H2', 'dept': 'D2', 'name': 'Dr2', 'phone': '13900000000',
        'passcode': '1234',
    }).get_json()['data']['token']
    second_auth = {'Authorization': f'Bearer {second_token}'}
    denied = client.post(
        '/devices',
        headers=second_auth,
        json={'device_code': 'INSOLE-001', 'device_name': '不得接管'},
    )

    assert denied.status_code == 403
    assert client.get('/devices', headers=first_auth).get_json()['data'] == [
        original.get_json()['data']
    ]
    assert client.get('/devices', headers=second_auth).get_json()['data'] == []
