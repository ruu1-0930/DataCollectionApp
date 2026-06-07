from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Clinician
from utils import Response, token_required
from auth import hash_passcode, verify_passcode, issue_token

clinician_bp = Blueprint('clinician', __name__)


def _clinician_public(c):
    return {'id': c.id, 'hospital': c.hospital, 'dept': c.dept,
            'name': c.name, 'phone': c.phone}


@clinician_bp.route('/clinician/enable', methods=['POST'])
def enable():
    data = request.json or {}
    required = ['hospital', 'dept', 'name', 'phone', 'terminal_code', 'passcode']
    if not all(data.get(k) for k in required):
        return jsonify(Response.error(400, "医院/科室/医生/手机/终端标识/口令均为必填")), 400

    existing = Clinician.query.filter_by(
        phone=data['phone'], terminal_code=data['terminal_code']).first()
    if existing:
        # 同手机同终端已启用：幂等重发 token，但必须先校验口令——
        # 红线（CLAUDE.md §3.2）：不得仅凭手机/终端签发 Token。口令不改。
        if not verify_passcode(data['passcode'], existing.passcode_hash):
            return jsonify(Response.error(401, "该终端已启用，口令不匹配")), 401
        return jsonify(Response.success(
            data={'token': issue_token(existing.id), 'clinician': _clinician_public(existing)},
            msg="该终端已启用"))

    c = Clinician(
        hospital=data['hospital'], dept=data['dept'], name=data['name'],
        phone=data['phone'], terminal_code=data['terminal_code'],
        passcode_hash=hash_passcode(data['passcode']))
    db.session.add(c)
    db.session.commit()
    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg="启用成功"))


@clinician_bp.route('/clinician/login', methods=['POST'])
def login():
    data = request.json or {}
    if not all(data.get(k) for k in ('phone', 'terminal_code', 'passcode')):
        return jsonify(Response.error(400, "手机/终端标识/口令均为必填")), 400

    c = Clinician.query.filter_by(
        phone=data['phone'], terminal_code=data['terminal_code']).first()
    if not c or not verify_passcode(data['passcode'], c.passcode_hash):
        return jsonify(Response.error(401, "口令或终端不匹配")), 401

    return jsonify(Response.success(
        data={'token': issue_token(c.id), 'clinician': _clinician_public(c)},
        msg="登录成功"))


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
    for field in ('hospital', 'dept', 'name', 'phone'):
        if data.get(field):
            setattr(c, field, data[field])
    db.session.commit()
    return jsonify(Response.success(data=_clinician_public(c), msg="资料已更新"))
