def _frame(**over):
    d = {
        **{f'lp{i}': i for i in range(1, 10)},
        'ax': 10, 'ay': 11, 'az': 12, 'gx': 13, 'gy': 14, 'gz': 15,
        'left_step_size': 16, 'left_speed': 17,
        'left_single_sp_time': 18, 'left_double_sp_time': 19,
        **{f'rp{i}': 100 + i for i in range(1, 10)},
        'right_ax': 110, 'right_ay': 111, 'right_az': 112,
        'right_gx': 113, 'right_gy': 114, 'right_gz': 115,
        'right_step_size': 116, 'right_speed': 117,
        'right_single_sp_time': 118, 'right_double_sp_time': 119,
    }
    d.update(over)
    return d


def _setup_with_data(client, n=3):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    for i in range(n):
        body = _frame(ax=i); body['patient_id'] = pid
        client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    return auth, pid


def test_history_returns_two_rows_per_frame_with_foot(client):
    # 每帧拆成左右两行，n 帧 → 2n 行
    auth, pid = _setup_with_data(client, n=3)
    resp = client.get(f'/patients/{pid}/data', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 6
    assert len(data['items']) == 6
    assert 'T1' in data['items'][0]['transformed']
    assert data['items'][0]['ax'] is not None
    assert set(it['foot'] for it in data['items']) == {'L', 'R'}


def test_history_pagination(client):
    auth, pid = _setup_with_data(client, n=5)
    resp = client.get(f'/patients/{pid}/data?page=1&page_size=2', headers=auth)
    data = resp.get_json()['data']
    assert data['total'] == 10
    assert len(data['items']) == 2


def test_history_other_clinician_forbidden(client):
    auth, pid = _setup_with_data(client, n=1)
    token2 = client.post('/clinician/enable', json={
        'hospital':'H','dept':'D','name':'Dr2','phone':'2','terminal_code':'t2','passcode':'1234'}).get_json()['data']['token']
    resp = client.get(f'/patients/{pid}/data', headers={'Authorization': f'Bearer {token2}'})
    assert resp.get_json()['code'] == 403
