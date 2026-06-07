def _setup_with_data(client, n=3):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    for i in range(n):
        client.post('/devices/INSOLE-001/raw_data', headers=auth,
                    json={'ax': i, 'ay': 2, 'az': 3, 'gx': 4, 'gy': 5, 'gz': 6, 'patient_id': pid})
    return auth, pid


def test_history_returns_items_with_transformed(client):
    auth, pid = _setup_with_data(client, n=3)
    resp = client.get(f'/patients/{pid}/data', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 3
    assert len(data['items']) == 3
    assert 'T1' in data['items'][0]['transformed']
    assert data['items'][0]['ax'] is not None


def test_history_pagination(client):
    auth, pid = _setup_with_data(client, n=5)
    resp = client.get(f'/patients/{pid}/data?page=1&page_size=2', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 5
    assert len(data['items']) == 2


def test_history_other_clinician_forbidden(client):
    auth, pid = _setup_with_data(client, n=1)
    token2 = client.post('/clinician/enable', json={
        'hospital':'H','dept':'D','name':'Dr2','phone':'2','terminal_code':'t2','passcode':'1234'}).get_json()['data']['token']
    resp = client.get(f'/patients/{pid}/data', headers={'Authorization': f'Bearer {token2}'})
    assert resp.get_json()['code'] == 403
