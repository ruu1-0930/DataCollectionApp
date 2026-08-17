def _lead_payload(**over):
    p = {'name': '李医生', 'hospital': '协和', 'dept': '康复科',
         'contact': '13900000000', 'intent': 'demo', 'message': '想试用'}
    p.update(over)
    return p


def test_create_lead_ok(client):
    resp = client.post('/leads', json=_lead_payload())
    assert resp.status_code == 200
    assert resp.get_json()['code'] == 200


def test_create_lead_persisted(client, db):
    from models.models import Lead
    client.post('/leads', json=_lead_payload())
    rows = Lead.query.all()
    assert len(rows) == 1
    assert rows[0].name == '李医生'
    assert rows[0].source == 'landing'


def test_create_lead_missing_name_rejected(client):
    resp = client.post('/leads', json=_lead_payload(name=''))
    assert resp.get_json()['code'] == 400


def test_create_lead_missing_contact_rejected(client):
    resp = client.post('/leads', json=_lead_payload(contact=''))
    assert resp.get_json()['code'] == 400


def test_unknown_intent_normalized_to_other(client, db):
    from models.models import Lead
    client.post('/leads', json=_lead_payload(intent='spam'))
    assert Lead.query.first().intent == 'other'


def test_honeypot_silently_dropped(client, db):
    # 蜜罐字段有值：返回成功但不入库
    from models.models import Lead
    resp = client.post('/leads', json=_lead_payload(website='http://bot'))
    assert resp.get_json()['code'] == 200
    assert Lead.query.count() == 0


def _token(client):
    resp = client.post('/clinician/enable', json={
        'hospital': '协和', 'dept': '骨科', 'name': '王医生',
        'phone': '13800000000', 'passcode': '1234'})
    return resp.get_json()['data']['token']


def test_list_leads_requires_token(client):
    resp = client.get('/leads')
    assert resp.status_code == 401


def test_list_leads_returns_items(client):
    client.post('/leads', json=_lead_payload())
    client.post('/leads', json=_lead_payload(name='张医生'))
    token = _token(client)
    resp = client.get('/leads', headers={'Authorization': f'Bearer {token}'})
    body = resp.get_json()
    assert body['data']['total'] == 2
    assert len(body['data']['items']) == 2
