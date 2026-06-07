from api.patient import format_subject_id


def test_format_subject_id():
    assert format_subject_id(1) == '#00001'
    assert format_subject_id(427) == '#00427'
    assert format_subject_id(123456) == '#123456'


def _token(client):
    resp = client.post('/clinician/enable', json={
        'hospital': 'H', 'dept': 'D', 'name': 'Dr', 'phone': '1',
        'terminal_code': 't', 'passcode': '1234'})
    return resp.get_json()['data']['token']


def _auth(client):
    return {'Authorization': f'Bearer {_token(client)}'}


def test_create_patient_assigns_subject_id(client):
    resp = client.post('/patients', headers=_auth(client),
                       json={'name': '张三', 'phone': '13900000000', 'gender': 'M', 'age': 40})
    data = resp.get_json()['data']
    assert data['subject_id'] == '#00001'
    assert data['id'] == 1
    assert data['existed'] is False


def test_create_patient_phone_required(client):
    resp = client.post('/patients', headers=_auth(client), json={'name': '张三'})
    assert resp.get_json()['code'] == 400


def test_create_patient_dedup_returns_existing(client):
    auth = _auth(client)
    client.post('/patients', headers=auth, json={'name': '张三', 'phone': '13900000000'})
    resp = client.post('/patients', headers=auth, json={'name': '张三', 'phone': '13900000000'})
    data = resp.get_json()['data']
    assert data['subject_id'] == '#00001'
    assert data['existed'] is True
