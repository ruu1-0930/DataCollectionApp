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
