import pytest

from config import create_app


@pytest.mark.parametrize(('setting', 'management_status'), [(None, 404), ('false', 404), ('true', 401)])
def test_data_management_routes_require_explicit_opt_in(monkeypatch, setting, management_status):
    if setting is None:
        monkeypatch.delenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', setting)
    app = create_app({'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:', 'TESTING': True})
    client = app.test_client()
    assert client.post('/v2/data-management/delete-previews').status_code == management_status
    assert client.post('/v2/data-exports').status_code == management_status
    assert client.post('/v2/patients').status_code == 401
    assert client.get('/v2/patients/1/collections').status_code == 401
