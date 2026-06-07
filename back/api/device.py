from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Device
from utils import Response, token_required

device_bp = Blueprint('device', __name__)


def _device_public(d):
    return {'id': d.id, 'device_code': d.device_code,
            'device_name': d.device_name, 'is_enabled': d.is_enabled}


@device_bp.route('/devices', methods=['POST'])
@token_required()
def register_device():
    """蓝牙连接成功后注册鞋垫（非扫码）。"""
    data = request.json or {}
    device_code = data.get('device_code')
    if not device_code:
        return jsonify(Response.error(400, "device_code 为必填")), 400

    existing = Device.query.filter_by(device_code=device_code).first()
    if existing:
        existing.clinician_id = g.clinician_id
        if data.get('device_name'):
            existing.device_name = data['device_name']
        db.session.commit()
        return jsonify(Response.success(data=_device_public(existing), msg="设备已注册"))

    d = Device(device_code=device_code, device_name=data.get('device_name'),
               clinician_id=g.clinician_id, is_enabled=True)
    db.session.add(d)
    db.session.commit()
    return jsonify(Response.success(data=_device_public(d), msg="设备注册成功"))


@device_bp.route('/devices', methods=['GET'])
@token_required()
def list_devices():
    devices = Device.query.filter_by(clinician_id=g.clinician_id).all()
    return jsonify(Response.success(data=[_device_public(d) for d in devices]))


@device_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@token_required()
def delete_device(device_id):
    d = Device.query.get(device_id)
    if not d:
        return jsonify(Response.error(404, "设备不存在")), 404
    if d.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权删除该设备")), 403
    db.session.delete(d)
    db.session.commit()
    return jsonify(Response.success(msg="设备已删除"))
