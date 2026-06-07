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
