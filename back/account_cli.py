"""Explicit server-only account administration; never runs at app startup."""

import getpass
import click
from flask.cli import with_appcontext
from sqlalchemy.exc import SQLAlchemyError

from auth import hash_passcode
from config import db
from models.models import Clinician
from services.clinician_validation import PHONE_PATTERN, valid_passcode
from services.admin_access_log import log_admin_event


@click.group('account')
def account_commands():
    """Create or explicitly change the role of an application account."""


def _record(action, result, **fields):
    log_admin_event(action=action, result=result, operator=getpass.getuser(), **fields)


@account_commands.command('create-admin')
@click.option('--hospital', prompt=True)
@click.option('--dept', prompt=True)
@click.option('--name', prompt=True)
@click.option('--phone', prompt=True)
@with_appcontext
def create_admin(hospital, dept, name, phone):
    values = {key: value.strip() for key, value in
              dict(hospital=hospital, dept=dept, name=name, phone=phone).items()}
    if (any(not value or len(value) > limit for value, limit in
            zip(values.values(), (100, 100, 50, 20))) or not PHONE_PATTERN.fullmatch(values['phone'])):
        raise click.ClickException('账号资料格式无效')
    passcode = click.prompt('Passcode', hide_input=True, confirmation_prompt=True).strip()
    if not valid_passcode(passcode):
        raise click.ClickException('口令格式无效')
    if not click.confirm('确认创建专用全局分析管理员？', default=False):
        _record('account.create', 'cancelled')
        raise click.Abort()
    try:
        if Clinician.query.filter_by(hospital=values['hospital'], phone=values['phone']).first():
            raise click.ClickException('该身份已存在；请按账号ID显式设置角色')
        actor = Clinician(**values, role='admin', passcode_hash=hash_passcode(passcode))
        db.session.add(actor)
        db.session.commit()
    except (SQLAlchemyError, click.ClickException) as exc:
        db.session.rollback()
        _record('account.create', 'failed')
        if isinstance(exc, click.ClickException):
            raise
        raise click.ClickException('账号创建失败，未更改已有账号') from None
    _record('account.create', 'succeeded', target_account_id=actor.id, new_role=actor.role)
    click.echo(f'ACCOUNT_CREATED id={actor.id} role={actor.role}')


@account_commands.command('set-role')
@click.option('--clinician-id', type=click.IntRange(min=1), required=True)
@click.option('--role', type=click.Choice(['clinician', 'admin']), required=True)
@with_appcontext
def set_role(clinician_id, role):
    actor = db.session.get(Clinician, clinician_id)
    if actor is None:
        raise click.ClickException('账号不存在')
    old_role = actor.role
    click.echo(f'ACCOUNT id={actor.id} current_role={old_role} requested_role={role}')
    if not click.confirm('确认该账号角色变更？', default=False):
        _record('account.set_role', 'cancelled', target_account_id=actor.id)
        raise click.Abort()
    if old_role == role:
        _record('account.set_role', 'unchanged', target_account_id=actor.id,
                previous_role=old_role, new_role=role)
        click.echo('ROLE_UNCHANGED')
        return
    try:
        actor.role = role
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        _record('account.set_role', 'failed', target_account_id=clinician_id)
        raise click.ClickException('角色变更失败，已回滚') from None
    _record('account.set_role', 'succeeded', target_account_id=actor.id,
            previous_role=old_role, new_role=role)
    click.echo(f'ROLE_UPDATED id={actor.id} role={role}')


def register_account_cli(app):
    app.cli.add_command(account_commands)
