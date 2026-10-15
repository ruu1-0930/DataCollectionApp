import os
import sys
import pytest

# 让 tests 能 import 到 back 根下的 config/app/models
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import create_app, db as _db


@pytest.fixture
def app():
    test_config = {
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'TESTING': True,
    }
    app = create_app(test_config)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def admin_scope(client, db):
    from models.models import Clinician
    result = {}
    for index, key in enumerate(('doctor_a', 'doctor_b', 'admin')):
        credentials = {'hospital': f'synthetic-hospital-{index}', 'dept': 'synthetic',
                       'name': f'synthetic-{key}', 'phone': f'1380000000{index}',
                       'passcode': 'synthetic-passcode'}
        response = client.post('/clinician/enable', json=credentials)
        assert response.status_code == 200
        data = response.get_json()['data']
        result[key] = {'id': data['clinician']['id'], 'credentials': credentials,
                       'headers': {'Authorization': 'Bearer ' + data['token']}}
    db.session.get(Clinician, result['admin']['id']).role = 'admin_readonly'
    db.session.commit()
    return result
