import pytest

from config import create_app, db


@pytest.mark.parametrize(('setting', 'management_status'), [(None, 404), ('false', 404), ('true', 401)])
def test_data_management_routes_require_explicit_opt_in(monkeypatch, tmp_path, setting, management_status):
    uri = "sqlite:///" + (tmp_path/"enabled.sqlite").as_posix()
    monkeypatch.delenv("SARCOGAIT_DATA_MANAGEMENT_ENABLED", raising=False)
    seed = create_app({"SQLALCHEMY_DATABASE_URI": uri, "TESTING": True})
    with seed.app_context():
        db.create_all()
    monkeypatch.setenv("SARCOGAIT_WORKBENCH_URL", "http://127.0.0.1:8000")
    if setting is None:
        monkeypatch.delenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', raising=False)
    else:
        monkeypatch.setenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', setting)
    app = create_app({'SQLALCHEMY_DATABASE_URI': uri, 'TESTING': True})
    client = app.test_client()
    assert client.post('/v2/data-management/delete-previews').status_code == management_status
    assert client.post('/v2/data-exports').status_code == management_status
    assert client.post('/v2/patients').status_code == 401
    assert client.get('/v2/patients/1/collections').status_code == 401


@pytest.mark.parametrize('url', ['', 'https://user:secret@example.test', 'file:///tmp/wb', 'https://wb.test?secret=x'])
def test_enabled_management_requires_server_workbench_origin(monkeypatch, url):
    monkeypatch.setenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', 'true')
    monkeypatch.setenv('SARCOGAIT_WORKBENCH_URL', url)
    with pytest.raises(RuntimeError, match='data_management_requires_SARCOGAIT_WORKBENCH_URL'):
        create_app({'SQLALCHEMY_DATABASE_URI':'sqlite:///:memory:', 'TESTING':True})


def test_009_only_cannot_enable_management(monkeypatch, tmp_path):
    from services.data_export import ExportGrant, ExportInventory
    uri = 'sqlite:///' + (tmp_path/'009.sqlite').as_posix()
    monkeypatch.delenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', raising=False)
    seed = create_app({'SQLALCHEMY_DATABASE_URI':uri, 'TESTING':True})
    with seed.app_context():
        db.create_all()
        ExportGrant.__table__.drop(db.engine)
        ExportInventory.__table__.drop(db.engine)
    monkeypatch.setenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED','true')
    monkeypatch.setenv('SARCOGAIT_WORKBENCH_URL','http://127.0.0.1:8000')
    with pytest.raises(RuntimeError, match='data_management_requires_migrations_009_010'):
        create_app({'SQLALCHEMY_DATABASE_URI':uri, 'TESTING':True})
