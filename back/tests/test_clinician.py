def _enable_payload(**over):
    p = {'hospital': '协和', 'dept': '骨科', 'name': '王医生',
         'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '1234'}
    p.update(over)
    return p


def test_enable_creates_clinician_and_returns_token(client):
    resp = client.post('/clinician/enable', json=_enable_payload())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['token']
    assert body['data']['clinician']['name'] == '王医生'
    assert 'passcode' not in body['data']['clinician']  # 不回传口令


def test_enable_missing_field_rejected(client):
    resp = client.post('/clinician/enable', json=_enable_payload(passcode=''))
    assert resp.get_json()['code'] == 400


def test_login_with_correct_passcode(client):
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/login', json={
        'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '1234'})
    assert resp.get_json()['data']['token']


def test_login_wrong_passcode_rejected(client):
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/login', json={
        'phone': '13800000000', 'terminal_code': 'term-1', 'passcode': '0000'})
    assert resp.get_json()['code'] != 200


def _token(client):
    resp = client.post('/clinician/enable', json=_enable_payload())
    return resp.get_json()['data']['token']


def test_get_me(client):
    token = _token(client)
    resp = client.get('/clinician/me', headers={'Authorization': f'Bearer {token}'})
    assert resp.get_json()['data']['name'] == '王医生'


def test_put_me_updates_dept(client):
    token = _token(client)
    resp = client.put('/clinician/me', headers={'Authorization': f'Bearer {token}'},
                      json={'dept': '康复科'})
    assert resp.get_json()['data']['dept'] == '康复科'


def test_me_requires_token(client):
    resp = client.get('/clinician/me')
    assert resp.status_code == 401
