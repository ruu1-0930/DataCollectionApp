from auth import hash_passcode, verify_passcode, issue_token, decode_token


def test_passcode_hash_roundtrip():
    h = hash_passcode('1234')
    assert h != '1234'              # 不存明文
    assert verify_passcode('1234', h) is True
    assert verify_passcode('9999', h) is False


def test_token_roundtrip(app):
    with app.app_context():
        token = issue_token(clinician_id=42)
        payload = decode_token(token)
        assert payload['clinician_id'] == 42
