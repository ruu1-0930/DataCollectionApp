import re

from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import IntegrityError

from config import db
from models.models import Clinician
from utils import Response, token_required
from auth import hash_passcode, verify_passcode, issue_token

clinician_bp = Blueprint('clinician', __name__)

_PHONE_PATTERN = re.compile(r'^1\d{10}$')
_LOGIN_FAILURE = '登录凭证不匹配'


def _clean_string(data, key):
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ''


def _valid_passcode(passcode):
    return len(passcode) >= 4


def _account_conflict():
    return jsonify(Response.error(409, '该医院手机号已被占用')), 409


def _clinician_public(c):
    return {'id': c.id, 'hospital': c.hospital, 'dept': c.dept,
            'name': c.name, 'phone': c.phone}


@clinician_bp.route('/clinician/enable', methods=['POST'])
def enable():
    data = request.json or {}
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
    data = request.json or {}
    hospital = _clean_string(data, 'hospital')
    name = _clean_string(data, 'name')
    phone = _clean_string(data, 'phone')
    passcode = _clean_string(data, 'passcode')
    if not all((hospital, name, phone, passcode)):
        return jsonify(Response.error(400, '医院/医生/手机/口令均为必填')), 400
    if not _PHONE_PATTERN.fullmatch(phone) or not _valid_passcode(passcode):
        return jsonify(Response.error(400, '手机号或口令格式无效')), 400

    c = Clinician.query.filter_by(hospital=hospital, phone=phone).first()
    if not c or name != c.name or not verify_passcode(passcode, c.passcode_hash):
        return jsonify(Response.error(401, _LOGIN_FAILURE)), 401

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
    data = request.json or {}
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
