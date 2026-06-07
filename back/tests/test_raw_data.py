def _setup(client):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    return auth, pid


def _sensor(**over):
    d = {'ax': 1, 'ay': 2, 'az': 3, 'gx': 4, 'gy': 5, 'gz': 6}
    d.update(over)
    return d


def test_upload_raw_data_attributes_and_runs_svm(client):
    auth, pid = _setup(client)
    body = _sensor(); body['patient_id'] = pid
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    data = resp.get_json()['data']
    assert data['raw_data_id'] >= 1
    assert 'T1' in data['transformed']


def test_upload_requires_patient_id(client):
    auth, pid = _setup(client)
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=_sensor())
    assert resp.get_json()['code'] == 400


def test_upload_unknown_device_404(client):
    auth, pid = _setup(client)
    body = _sensor(); body['patient_id'] = pid
    resp = client.post('/devices/NOPE/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 404


def test_upload_extra_38_fields_ignored(client):
    auth, pid = _setup(client)
    body = _sensor(lp1=9, right_ax=8); body['patient_id'] = pid
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 200
