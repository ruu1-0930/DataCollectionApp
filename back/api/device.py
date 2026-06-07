import datetime
from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Device
from models.models import Patient, DeviceRawData, DeviceTransformedData
from api.analysis import analyze
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


@device_bp.route('/devices/<string:device_code>/raw_data', methods=['POST'])
@token_required()
def upload_raw_data(device_code):
    device = Device.query.filter_by(device_code=device_code,
                                    clinician_id=g.clinician_id).first()
    if not device:
        return jsonify(Response.error(404, "设备不存在或不属于当前医护")), 404

    data = request.json or {}
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify(Response.error(400, "patient_id 为必填")), 400

    patient = Patient.query.get(patient_id)
    if not patient or patient.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "患者不存在或不属于当前医护")), 403

    try:
        ax = float(data['ax']); ay = float(data['ay']); az = float(data['az'])
        gx = float(data['gx']); gy = float(data['gy']); gz = float(data['gz'])
    except (KeyError, TypeError, ValueError):
        return jsonify(Response.error(400, "缺少或非法的 6 轴传感器字段")), 400

    now = datetime.datetime.utcnow()
    raw = DeviceRawData(device_id=device.id, patient_id=patient.id,
                        clinician_id=g.clinician_id,
                        ax=ax, ay=ay, az=az, gx=gx, gy=gy, gz=gz,
                        collected_at=now, uploaded_at=now)
    db.session.add(raw)
    db.session.flush()

    T1, T2, T3, T4, T5 = analyze(ax, ay, az, gx, gy, gz)
    db.session.add(DeviceTransformedData(raw_data_id=raw.id,
                                         T1=T1, T2=T2, T3=T3, T4=T4, T5=T5))
    patient.last_collected_at = now
    db.session.commit()

    return jsonify(Response.success(
        data={'raw_data_id': raw.id,
              'transformed': {'T1': T1, 'T2': T2, 'T3': T3, 'T4': T4, 'T5': T5}},
        msg="数据上传成功"))
