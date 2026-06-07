from flask import g
from auth import issue_token
from utils import token_required
from models.models import Clinician
from config import db


def _make_clinician():
    c = Clinician(hospital='H', dept='D', name='Dr', phone='1',
                  terminal_code='t', passcode_hash='x')
    db.session.add(c); db.session.commit()
    return c


def test_token_required_sets_clinician_id(app):
    with app.app_context():
        c = _make_clinician()
        token = issue_token(c.id)

        @token_required()
        def view():
            return {'cid': g.clinician_id}

        with app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            assert view()['cid'] == c.id


def test_token_required_missing_token(app):
    with app.app_context():
        @token_required()
        def view():
            return 'ok'

        with app.test_request_context():
            resp, status = view()
            assert status == 401
