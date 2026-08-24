import pytest
from sqlalchemy.exc import IntegrityError

from api import clinician as clinician_api
from auth import hash_passcode
from config import db
from models.models import Clinician


def _enable_payload(**overrides):
    payload = {
        'hospital': '协和医院',
        'dept': '骨科',
        'name': '王医生',
        'phone': '13800000000',
        'passcode': '1234',
    }
    payload.update(overrides)
    return payload


def _login_payload(**overrides):
    payload = {
        'hospital': '协和医院',
        'name': '王医生',
        'phone': '13800000000',
        'passcode': '1234',
    }
    payload.update(overrides)
    return payload


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


def test_login_uses_hospital_name_phone_and_passcode(client):
    client.post('/clinician/enable', json=_enable_payload())
    response = client.post('/clinician/login', json=_login_payload())
    assert response.status_code == 200
    assert response.get_json()['data']['token']


def test_login_name_and_passcode_fail_with_same_generic_message(client):
    client.post('/clinician/enable', json=_enable_payload())
    wrong_name = client.post(
        '/clinician/login', json=_login_payload(name='其他医生'))
    wrong_passcode = client.post(
        '/clinician/login', json=_login_payload(passcode='9999'))
    assert wrong_name.status_code == 401
    assert wrong_passcode.status_code == 401
    assert wrong_name.get_json()['msg'] == wrong_passcode.get_json()['msg']


def test_login_rejects_bad_phone_and_short_passcode(client):
    bad_phone = client.post('/clinician/login', json=_login_payload(phone='123'))
    short_passcode = client.post('/clinician/login', json=_login_payload(passcode='123'))
    assert bad_phone.status_code == 400
    assert short_passcode.status_code == 400


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/clinician/enable", []),
        ("/clinician/enable", "not-an-object"),
        ("/clinician/enable", None),
        ("/clinician/enable", {}),
        ("/clinician/login", []),
        ("/clinician/login", "not-an-object"),
        ("/clinician/login", None),
        ("/clinician/login", {}),
    ],
)
def test_enable_and_login_reject_non_object_json_as_bad_request(client, path, payload):
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    response = client.post(path, json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize("path", ["/clinician/enable", "/clinician/login"])
def test_enable_and_login_reject_malformed_json_as_bad_request(client, path):
    response = client.post(path, data="{", content_type="application/json")
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/clinician/enable", _enable_payload(terminal_code="legacy")),
        ("/clinician/login", _login_payload(terminal_code="legacy")),
    ],
)
def test_enable_and_login_reject_unknown_json_fields(client, path, payload):
    if path.endswith("login"):
        client.post("/clinician/enable", json=_enable_payload())
    response = client.post(path, json=payload)
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/clinician/enable", {"hospital": "协和医院"}),
        ("/clinician/login", {"hospital": "协和医院"}),
    ],
)
def test_enable_and_login_reject_missing_json_fields(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 400


def test_profile_update_rejects_empty_or_unknown_json_fields(client):
    token = _token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.application.config["PROPAGATE_EXCEPTIONS"] = False
    for payload in (
        [],
        "not-an-object",
        None,
        {},
        {"terminal_code": "legacy"},
        {"dept": "  "},
    ):
        response = client.put("/clinician/me", headers=headers, json=payload)
        assert response.status_code == 400


def test_profile_update_rejects_malformed_json_as_bad_request(client):
    token = _token(client)
    response = client.put(
        "/clinician/me",
        headers={"Authorization": f"Bearer {token}"},
        data="{",
        content_type="application/json",
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    ("passcode", "expected_status"),
    [
        ("a" * 72, 200),
        ("a" * 73, 400),
        ("密" * 24, 200),
        ("密" * 25, 400),
    ],
)
def test_enable_enforces_utf8_passcode_byte_limit(client, passcode, expected_status):
    response = client.post(
        "/clinician/enable",
        json=_enable_payload(phone="13600000000", passcode=passcode),
    )
    assert response.status_code == expected_status


def test_enable_reissue_requires_correct_passcode(client):
    # 同一医院和手机号再次启用：口令正确才幂等重发 token
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/enable', json=_enable_payload())
    assert resp.get_json()['code'] == 200
    assert resp.get_json()['data']['token']


def test_enable_reissue_wrong_passcode_rejected(client):
    # 红线：已启用账户用错口令再启用，不得签发 token
    client.post('/clinician/enable', json=_enable_payload())
    resp = client.post('/clinician/enable', json=_enable_payload(passcode='9999'))
    assert resp.get_json()['code'] == 401
    assert resp.get_json().get('data') is None


def test_enable_existing_account_wrong_name_rejected(client):
    client.post('/clinician/enable', json=_enable_payload())
    response = client.post(
        '/clinician/enable',
        json=_enable_payload(name='其他医生'),
    )
    assert response.status_code == 401
    assert response.get_json()['msg'] == '登录凭证不匹配'


def test_enable_trims_identity_fields_for_account_and_login(client):
    enabled = client.post(
        '/clinician/enable',
        json=_enable_payload(
            hospital='  协和医院  ',
            dept='  骨科  ',
            name='  王医生  ',
            phone='  13600000000  ',
            passcode='  1234  ',
        ),
    )
    assert enabled.status_code == 200
    clinician = enabled.get_json()['data']['clinician']
    assert clinician['hospital'] == '协和医院'
    assert clinician['dept'] == '骨科'
    assert clinician['name'] == '王医生'
    assert clinician['phone'] == '13600000000'

    logged_in = client.post(
        '/clinician/login',
        json=_login_payload(
            hospital='  协和医院  ',
            name='  王医生  ',
            phone='  13600000000  ',
            passcode='  1234  ',
        ),
    )
    assert logged_in.status_code == 200


def test_hospital_is_part_of_clinician_identity(client):
    first = client.post(
        '/clinician/enable',
        json=_enable_payload(hospital='协和医院', phone='13500000000'),
    )
    second = client.post(
        '/clinician/enable',
        json=_enable_payload(hospital='卋和医院', name='李医生', phone='13500000000'),
    )
    assert first.status_code == second.status_code == 200

    response = client.post(
        '/clinician/login',
        json=_login_payload(hospital='卋和医院', name='李医生', phone='13500000000'),
    )
    assert response.status_code == 200
    assert response.get_json()['data']['clinician']['hospital'] == '卋和医院'


def test_unknown_name_and_passcode_mismatches_share_one_failure_message(client):
    client.post('/clinician/enable', json=_enable_payload())
    responses = [
        client.post('/clinician/login', json=_login_payload(phone='13400000000')),
        client.post('/clinician/login', json=_login_payload(name='其他医生')),
        client.post('/clinician/login', json=_login_payload(passcode='9999')),
    ]
    assert [response.status_code for response in responses] == [401, 401, 401]
    assert {response.get_json()['msg'] for response in responses} == {'登录凭证不匹配'}


def test_enable_race_rechecks_matching_account_and_issues_token(client, monkeypatch):
    original_commit = db.session.commit

    def commit_after_matching_account_wins():
        db.session.rollback()
        db.session.add(Clinician(
            hospital='协和医院',
            dept='骨科',
            name='王医生',
            phone='13300000000',
            passcode_hash=hash_passcode('1234'),
        ))
        original_commit()
        raise IntegrityError('simulated unique conflict', None, None)

    monkeypatch.setattr(db.session, 'commit', commit_after_matching_account_wins)
    response = client.post('/clinician/enable', json=_enable_payload(phone='13300000000'))
    assert response.status_code == 200
    assert response.get_json()['data']['token']


@pytest.mark.parametrize(
    ('raced_name', 'raced_passcode'),
    [('其他医生', '1234'), ('王医生', '9999')],
)
def test_enable_race_rejects_mismatched_existing_account(
    client,
    monkeypatch,
    raced_name,
    raced_passcode,
):
    original_commit = db.session.commit

    def commit_after_mismatched_account_wins():
        db.session.rollback()
        db.session.add(Clinician(
            hospital='协和医院',
            dept='骨科',
            name=raced_name,
            phone='13200000000',
            passcode_hash=hash_passcode(raced_passcode),
        ))
        original_commit()
        raise IntegrityError('simulated unique conflict', None, None)

    monkeypatch.setattr(db.session, 'commit', commit_after_mismatched_account_wins)
    response = client.post('/clinician/enable', json=_enable_payload(phone='13200000000'))
    assert response.status_code == 401
    assert response.get_json()['msg'] == '登录凭证不匹配'


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


def test_profile_update_rejects_duplicate_hospital_phone(client):
    first = client.post('/clinician/enable', json=_enable_payload(phone='13800000000'))
    second = client.post(
        '/clinician/enable',
        json=_enable_payload(name='李医生', phone='13900000000'),
    )
    assert first.status_code == second.status_code == 200
    second_token = second.get_json()['data']['token']
    response = client.put(
        '/clinician/me',
        headers={'Authorization': f'Bearer {second_token}'},
        json={'phone': '13800000000'},
    )
    assert response.status_code == 409
    assert response.get_json()['code'] == 409


def test_profile_update_reraises_integrity_error_without_conflict(client, monkeypatch):
    token = _token(client)
    error = IntegrityError('simulated unrelated failure', None, None)
    monkeypatch.setattr(db.session, 'commit', lambda: (_ for _ in ()).throw(error))

    with pytest.raises(IntegrityError) as raised:
        client.put(
            '/clinician/me',
            headers={'Authorization': f'Bearer {token}'},
            json={'phone': '13100000000'},
        )
    assert raised.value is error


def test_me_requires_token(client):
    resp = client.get('/clinician/me')
    assert resp.status_code == 401


def test_missing_account_verifies_against_fixed_dummy_bcrypt_hash(client, monkeypatch):
    verified_hashes = []
    original_verify = clinician_api.verify_passcode

    def observe_verification(passcode, passcode_hash):
        verified_hashes.append(passcode_hash)
        return original_verify(passcode, passcode_hash)

    monkeypatch.setattr(clinician_api, 'verify_passcode', observe_verification)
    response = client.post('/clinician/login', json=_login_payload(phone='13000000000'))

    assert response.status_code == 401
    assert verified_hashes == [clinician_api._DUMMY_PASSCODE_HASH]


def test_login_rate_limit_uses_injected_clock_and_success_clears_failures(client):
    clock = [1000.0]
    client.application.config.update(
        LOGIN_FAILURE_LIMIT=2,
        LOGIN_FAILURE_WINDOW_SECONDS=10,
        LOGIN_RATE_LIMIT_CLOCK=lambda: clock[0],
    )
    client.post('/clinician/enable', json=_enable_payload())

    first_failure = client.post(
        '/clinician/login', json=_login_payload(passcode='9999'),
        environ_base={'REMOTE_ADDR': '192.0.2.10'},
    )
    successful_login = client.post(
        '/clinician/login', json=_login_payload(),
        environ_base={'REMOTE_ADDR': '192.0.2.10'},
    )
    subsequent_failures = [
        client.post(
            '/clinician/login', json=_login_payload(passcode='9999'),
            environ_base={'REMOTE_ADDR': '192.0.2.10'},
        )
        for _ in range(3)
    ]

    assert first_failure.status_code == 401
    assert successful_login.status_code == 200
    assert [response.status_code for response in subsequent_failures] == [401, 401, 429]


def test_login_rate_limit_defaults_to_five_failures_per_ip_and_window(client):
    clock = [1000.0]
    client.application.config['LOGIN_RATE_LIMIT_CLOCK'] = lambda: clock[0]
    payload = _login_payload(phone='13000000000')

    first_ip = [
        client.post(
            '/clinician/login', json=payload,
            environ_base={'REMOTE_ADDR': '192.0.2.10'},
        )
        for _ in range(6)
    ]
    other_ip = client.post(
        '/clinician/login', json=payload,
        environ_base={'REMOTE_ADDR': '192.0.2.11'},
    )
    clock[0] += 301
    after_window = client.post(
        '/clinician/login', json=payload,
        environ_base={'REMOTE_ADDR': '192.0.2.10'},
    )

    assert [response.status_code for response in first_ip] == [401, 401, 401, 401, 401, 429]
    assert other_ip.status_code == 401
    assert after_window.status_code == 401
