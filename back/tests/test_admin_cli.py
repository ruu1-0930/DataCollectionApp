"""Account CLI never elevates by registration or exposes a credential."""

from models.models import Clinician
from auth import verify_passcode


CREATE = ['account', 'create-admin', '--hospital', 'synthetic-admin-hospital',
          '--dept', 'synthetic', '--name', 'synthetic-admin', '--phone', '13800000009']


def test_create_admin_requires_confirmation_and_hides_passcode(app):
    result = app.test_cli_runner().invoke(args=CREATE, input='synthetic-secret\nsynthetic-secret\ny\n')
    assert result.exit_code == 0
    actor = Clinician.query.filter_by(phone='13800000009').one()
    assert actor.role == 'admin'
    assert verify_passcode('synthetic-secret', actor.passcode_hash)
    assert 'synthetic-secret' not in result.output
    assert 'token' not in result.output.lower()


def test_create_admin_cancel_has_no_account(app):
    result = app.test_cli_runner().invoke(args=CREATE, input='synthetic-secret\nsynthetic-secret\nn\n')
    assert result.exit_code != 0
    assert Clinician.query.count() == 0


def test_set_role_and_revoke_are_explicit_and_repeatable(app, admin_scope):
    actor = admin_scope['doctor_a']
    runner = app.test_cli_runner()
    args = ['account', 'set-role', '--clinician-id', str(actor['id']), '--role', 'admin']
    cancelled = runner.invoke(args=args, input='n\n')
    assert cancelled.exit_code != 0
    assert Clinician.query.get(actor['id']).role == 'clinician'
    assert runner.invoke(args=args, input='y\n').exit_code == 0
    assert runner.invoke(args=args, input='y\n').exit_code == 0
    assert Clinician.query.get(actor['id']).role == 'admin'
    args[-1] = 'clinician'
    assert runner.invoke(args=args, input='y\n').exit_code == 0
    assert Clinician.query.get(actor['id']).role == 'clinician'


def test_create_duplicate_admin_does_not_change_existing_account(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=CREATE, input='synthetic-secret\nsynthetic-secret\ny\n').exit_code == 0
    original = Clinician.query.one().passcode_hash
    again = runner.invoke(args=CREATE, input='different-secret\ndifferent-secret\ny\n')
    assert again.exit_code != 0
    assert Clinician.query.count() == 1
    assert Clinician.query.one().passcode_hash == original


def test_create_admin_database_failure_rolls_back_without_exception_details(app, db, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    def fail_commit():
        raise SQLAlchemyError('synthetic-sensitive-sql-details')

    monkeypatch.setattr(db.session, 'commit', fail_commit)
    result = app.test_cli_runner().invoke(args=CREATE, input='synthetic-secret\nsynthetic-secret\ny\n')
    assert result.exit_code != 0
    assert Clinician.query.count() == 0
    assert 'synthetic-sensitive-sql-details' not in result.output
    assert 'synthetic-secret' not in result.output
