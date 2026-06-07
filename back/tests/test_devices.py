def _auth(client):
    token = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr', 'phone': '1',
        'terminal_code': 't', 'passcode': '1234'}).get_json()['data']['token']
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
