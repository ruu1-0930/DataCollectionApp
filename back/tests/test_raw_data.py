from models.models import DeviceRawData


def _setup(client):
    auth = {'Authorization': f"Bearer {client.post('/clinician/enable', json={'hospital':'H','dept':'D','name':'Dr','phone':'1','terminal_code':'t','passcode':'1234'}).get_json()['data']['token']}"}
    pid = client.post('/patients', headers=auth, json={'name': 'A', 'phone': '111'}).get_json()['data']['id']
    client.post('/devices', headers=auth, json={'device_code': 'INSOLE-001'})
    return auth, pid


def _frame(**over):
    """设备一帧 = 合并 38 字段（前 19 左脚 / 后 19 右脚），字段名沿用 App apiData。"""
    d = {
        # 左脚压力 lp1..lp9 = 1..9
        **{f'lp{i}': i for i in range(1, 10)},
        # 左脚 IMU
        'ax': 10, 'ay': 11, 'az': 12, 'gx': 13, 'gy': 14, 'gz': 15,
        # 左脚步态
        'left_step_size': 16, 'left_speed': 17,
        'left_single_sp_time': 18, 'left_double_sp_time': 19,
        # 右脚压力 rp1..rp9 = 101..109
        **{f'rp{i}': 100 + i for i in range(1, 10)},
        # 右脚 IMU
        'right_ax': 110, 'right_ay': 111, 'right_az': 112,
        'right_gx': 113, 'right_gy': 114, 'right_gz': 115,
        # 右脚步态
        'right_step_size': 116, 'right_speed': 117,
        'right_single_sp_time': 118, 'right_double_sp_time': 119,
    }
    d.update(over)
    return d


def test_upload_creates_two_rows_split_left_right(client):
    auth, pid = _setup(client)
    body = _frame(); body['patient_id'] = pid
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    data = resp.get_json()['data']
    assert data['left']['raw_data_id'] >= 1
    assert data['right']['raw_data_id'] >= 1
    assert data['left']['raw_data_id'] != data['right']['raw_data_id']

    rows = DeviceRawData.query.order_by(DeviceRawData.id).all()
    assert len(rows) == 2
    left = next(r for r in rows if r.foot == 'L')
    right = next(r for r in rows if r.foot == 'R')

    # 左脚 19 字段映射
    assert (left.p1, left.p9) == (1, 9)
    assert (left.ax, left.gz) == (10, 15)
    assert left.step_length == 16 and left.double_support_time == 19
    # 右脚 19 字段映射
    assert (right.p1, right.p9) == (101, 109)
    assert (right.ax, right.gz) == (110, 115)
    assert right.step_length == 116 and right.double_support_time == 119
    # 两行共享同一采集时刻
    assert left.collected_at == right.collected_at


def test_upload_runs_svm_per_foot(client):
    auth, pid = _setup(client)
    body = _frame(); body['patient_id'] = pid
    data = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body).get_json()['data']
    assert 'T1' in data['left']['transformed']
    assert 'T1' in data['right']['transformed']


def test_upload_requires_patient_id(client):
    auth, pid = _setup(client)
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=_frame())
    assert resp.get_json()['code'] == 400


def test_upload_unknown_device_404(client):
    auth, pid = _setup(client)
    body = _frame(); body['patient_id'] = pid
    resp = client.post('/devices/NOPE/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 404


def test_upload_missing_field_400(client):
    auth, pid = _setup(client)
    body = _frame(); body['patient_id'] = pid
    del body['rp5']  # 缺一个右脚压力
    resp = client.post('/devices/INSOLE-001/raw_data', headers=auth, json=body)
    assert resp.get_json()['code'] == 400
