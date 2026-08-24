import re

from flask import Blueprint, current_app, request, jsonify, g
from sqlalchemy.exc import IntegrityError

from config import db
from models.models import Clinician
from utils import Response, token_required
from auth import hash_passcode, verify_passcode, issue_token

clinician_bp = Blueprint('clinician', __name__)

_PHONE_PATTERN = re.compile(r'^1\d{10}$')
_LOGIN_FAILURE = '登录凭证不匹配'
_DUMMY_PASSCODE_HASH = '$2b$12$gouvJor73kG.F3wLSOsJV.HoeEmpe2dQ/mOst3SFP/smhqimC1456'
_ENABLE_FIELDS = frozenset({'hospital', 'dept', 'name', 'phone', 'passcode'})
_LOGIN_FIELDS = frozenset({'hospital', 'name', 'phone', 'passcode'})
_PROFILE_FIELDS = frozenset({'hospital', 'dept', 'name', 'phone'})


def _clean_string(data, key):
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ''


def _valid_passcode(passcode):
    try:
        return len(passcode) >= 4 and len(passcode.encode('utf-8')) <= 72
    except UnicodeEncodeError:
        return False


def _json_object_with_allowed_fields(allowed_fields, *, exact):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    keys = set(data)
    if (exact and keys != allowed_fields) or (
        not exact and (not keys or not keys.issubset(allowed_fields))
    ):
        return None
    return data


def _invalid_json_fields_response():
    return jsonify(Response.error(400, '请求字段无效')), 400


def _account_conflict():
    return jsonify(Response.error(409, '该医院手机号已被占用')), 409


def _clinician_public(c):
    return {'id': c.id, 'hospital': c.hospital, 'dept': c.dept,
            'name': c.name, 'phone': c.phone}


def _login_failure_key(hospital, phone):
    return request.remote_addr or '', hospital, phone


def _login_failure_attempts(key, now):
    window = current_app.config['LOGIN_FAILURE_WINDOW_SECONDS']
    attempts = current_app.extensions['login_failure_windows'].get(key, [])
    attempts = [attempt for attempt in attempts if attempt > now - window]
    if attempts:
        current_app.extensions['login_failure_windows'][key] = attempts
    else:
        current_app.extensions['login_failure_windows'].pop(key, None)
    return attempts


def _login_rate_limited(key, now):
    return len(_login_failure_attempts(key, now)) >= current_app.config['LOGIN_FAILURE_LIMIT']


def _record_login_failure(key, now):
    attempts = _login_failure_attempts(key, now)
    attempts.append(now)
    current_app.extensions['login_failure_windows'][key] = attempts


def _clear_login_failures(key):
    current_app.extensions['login_failure_windows'].pop(key, None)


@clinician_bp.route('/clinician/enable', methods=['POST'])
def enable():
    data = _json_object_with_allowed_fields(_ENABLE_FIELDS, exact=True)
    if data is None:
        return _invalid_json_fields_response()
    hospital = _clean_string(data, 'hospital')
    dept = _clean_string(data, 'dept')
    name = _clean_string(data, 'name')
    phone = _clean_string(data, 'phone')
    passcode = _clean_string(data, 'passcode')
    if not all((hospital, dept, name, phone, passcode)):
        return jsonify(Response.error(400, '医院/科室/医生/手机/口令均为必填')), 400
    if not _PHONE_PATTERN.fullmatch(phone) or not _valid_passcode(passcode):
        return jsonify(Response.error(400, '手机号或口令格式无效')), 400

    existing = Clinician.query.filter_by(hospital=hospital, phone=phone).first()
    if existing:
        if name != existing.name or not verify_passcode(passcode, existing.passcode_hash):
            return jsonify(Response.error(401, _LOGIN_FAILURE)), 401
        return jsonify(Response.success(
            data={'token': issue_token(existing.id), 'clinician': _clinician_public(existing)},
            msg='账户已启用'))

    c = Clinician(
        hospital=hospital, dept=dept, name=name, phone=phone,
        passcode_hash=hash_passcode(passcode))
    db.session.add(c)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = Clinician.query.filter_by(hospital=hospital, phone=phone).first()
        if not existing or name != existing.name or not verify_passcode(passcode, existing.passcode_hash):
            return jsonify(Response.error(401, _LOGIN_FAILURE)), 401
        return jsonify(Response.success(
            data={'token': issue_token(existing.id), 'clinician': _clinician_public(existing)},
            msg='账户已启用'))
    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg='启用成功'))


@clinician_bp.route('/clinician/login', methods=['POST'])
def login():
    data = _json_object_with_allowed_fields(_LOGIN_FIELDS, exact=True)
    if data is None:
        return _invalid_json_fields_response()
    hospital = _clean_string(data, 'hospital')
    name = _clean_string(data, 'name')
    phone = _clean_string(data, 'phone')
    passcode = _clean_string(data, 'passcode')
    if not all((hospital, name, phone, passcode)):
        return jsonify(Response.error(400, '医院/医生/手机/口令均为必填')), 400
    if not _PHONE_PATTERN.fullmatch(phone) or not _valid_passcode(passcode):
        return jsonify(Response.error(400, '手机号或口令格式无效')), 400

    key = _login_failure_key(hospital, phone)
    now = current_app.config['LOGIN_RATE_LIMIT_CLOCK']()
    if _login_rate_limited(key, now):
        return jsonify(Response.error(429, '登录尝试次数过多，请稍后再试')), 429

    c = Clinician.query.filter_by(hospital=hospital, phone=phone).first()
    passcode_hash = c.passcode_hash if c is not None else _DUMMY_PASSCODE_HASH
    passcode_matches = verify_passcode(passcode, passcode_hash)
    if not c or name != c.name or not passcode_matches:
        _record_login_failure(key, now)
        return jsonify(Response.error(401, _LOGIN_FAILURE)), 401

    _clear_login_failures(key)
    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg='登录成功'))


@clinician_bp.route('/clinician/me', methods=['GET'])
@token_required()
def get_me():
    c = Clinician.query.get(g.clinician_id)
    return jsonify(Response.success(data=_clinician_public(c)))


@clinician_bp.route('/clinician/me', methods=['PUT'])
@token_required()
def update_me():
    c = Clinician.query.get(g.clinician_id)
    data = _json_object_with_allowed_fields(_PROFILE_FIELDS, exact=False)
    if data is None:
        return _invalid_json_fields_response()
    updates = {}
    for field in ('hospital', 'dept', 'name', 'phone'):
        if field in data:
            value = _clean_string(data, field)
            if not value:
                return jsonify(Response.error(400, '资料字段不能为空')), 400
            updates[field] = value

    if 'phone' in updates and not _PHONE_PATTERN.fullmatch(updates['phone']):
        return jsonify(Response.error(400, '手机号格式无效')), 400

    hospital = updates.get('hospital', c.hospital)
    phone = updates.get('phone', c.phone)
    conflict = Clinician.query.filter(
        Clinician.hospital == hospital,
        Clinician.phone == phone,
        Clinician.id != c.id,
    ).first()
    if conflict:
        return _account_conflict()

    for field, value in updates.items():
        setattr(c, field, value)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        conflict = Clinician.query.filter(
            Clinician.hospital == hospital,
            Clinician.phone == phone,
            Clinician.id != c.id,
        ).first()
        if conflict:
            return _account_conflict()
        raise
    return jsonify(Response.success(data=_clinician_public(c), msg='资料已更新'))
