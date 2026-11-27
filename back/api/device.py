import datetime
from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import IntegrityError
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
@token_required('clinician.write')
def register_device():
    """蓝牙连接成功后注册鞋垫（非扫码）。"""
    data = request.json or {}
    device_code = data.get('device_code')
    if not device_code:
        return jsonify(Response.error(400, "device_code 为必填")), 400

    registration = Device.query.filter_by(clinician_id=g.clinician_id, device_code=device_code)
    existing = registration.one_or_none()
    if existing:
        if not existing.is_enabled:
            existing.is_enabled = True
            db.session.commit()
        return jsonify(Response.success(data=_device_public(existing), msg="设备已注册"))

    d = Device(device_code=device_code, device_name=data.get('device_name'),
               clinician_id=g.clinician_id, is_enabled=True)
    db.session.add(d)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = registration.one_or_none()
        if existing is None:
            raise
        return jsonify(Response.success(data=_device_public(existing), msg="设备已注册"))
    return jsonify(Response.success(data=_device_public(d), msg="设备注册成功"))


@device_bp.route('/devices', methods=['GET'])
@token_required()
def list_devices():
    devices = Device.query.filter_by(clinician_id=g.clinician_id, is_enabled=True).all()
    return jsonify(Response.success(data=[_device_public(d) for d in devices]))


@device_bp.route('/devices/<int:device_id>', methods=['DELETE'])
@token_required('clinician.write')
def delete_device(device_id):
    d = Device.query.get(device_id)
    if not d:
        return jsonify(Response.error(404, "设备不存在")), 404
    if d.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权删除该设备")), 403
    d.is_enabled = False
    db.session.commit()
    return jsonify(Response.success(msg="设备已解绑"))


# 一帧 BLE = 合并 38 字段：前 19 左脚、后 19 右脚（硬件固定顺序）。
# 摄取时按 schema 列 → App apiData 源字段名 拆成两条每脚记录。
_LEFT_SRC = {
    **{f'p{i}': f'lp{i}' for i in range(1, 10)},
    'ax': 'ax', 'ay': 'ay', 'az': 'az', 'gx': 'gx', 'gy': 'gy', 'gz': 'gz',
    'step_length': 'left_step_size', 'walking_speed': 'left_speed',
    'single_support_time': 'left_single_sp_time', 'double_support_time': 'left_double_sp_time',
}
_RIGHT_SRC = {
    **{f'p{i}': f'rp{i}' for i in range(1, 10)},
    'ax': 'right_ax', 'ay': 'right_ay', 'az': 'right_az',
    'gx': 'right_gx', 'gy': 'right_gy', 'gz': 'right_gz',
    'step_length': 'right_step_size', 'walking_speed': 'right_speed',
    'single_support_time': 'right_single_sp_time', 'double_support_time': 'right_double_sp_time',
}


def _parse_foot(data, src_map):
    return {col: float(data[key]) for col, key in src_map.items()}


@device_bp.route('/devices/<string:device_code>/raw_data', methods=['POST'])
@token_required('clinician.write')
def upload_raw_data(device_code):
    device = Device.query.filter_by(device_code=device_code,
                                    clinician_id=g.clinician_id).first()
    if not device:
        return jsonify(Response.error(404, "设备不存在或不属于当前医护")), 404

    data = request.json or {}
    patient_id = data.get('patient_id')
    if not patient_id:
        return jsonify(Response.error(400, "patient_id 为必填")), 400

    from services.collection_ingest import write_transaction
    from services.data_management_scope import assert_clinical_scope
    from access import AccessError
    try:
        with write_transaction() as session:
            patient = session.query(Patient).filter_by(id=patient_id).with_for_update().one_or_none()
            if patient is not None and patient.clinician_id != g.clinician_id:
                return jsonify(Response.error(403, "患者不存在或不属于当前医护")), 403
            assert_clinical_scope(session, patient_id)
            if patient is None:
                return jsonify(Response.error(403, "患者不存在或不属于当前医护")), 403
            if not db.session.query(Device).filter_by(id=device.id, is_enabled=True).with_for_update().populate_existing().first():
                return jsonify(Response.error(404, "设备未绑定")), 404
            try:
                feet = {'L': _parse_foot(data, _LEFT_SRC), 'R': _parse_foot(data, _RIGHT_SRC)}
            except (KeyError, TypeError, ValueError):
                return jsonify(Response.error(400, "缺少或非法的 38 字段（每脚 9 压力 + 6 IMU + 4 步态）")), 400

            now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).replace(tzinfo=None)
            result = {}
            for foot, vals in feet.items():
                raw = DeviceRawData(device_id=device.id, patient_id=patient.id,
                                    clinician_id=g.clinician_id, foot=foot,
                                    collected_at=now, uploaded_at=now, **vals)
                session.add(raw)
                session.flush()
                T1, T2, T3, T4, T5 = analyze(vals['ax'], vals['ay'], vals['az'],
                                             vals['gx'], vals['gy'], vals['gz'])
                session.add(DeviceTransformedData(raw_data_id=raw.id, T1=T1, T2=T2, T3=T3, T4=T4, T5=T5))
                result['left' if foot == 'L' else 'right'] = {
                    'raw_data_id': raw.id,
                    'transformed': {'T1': T1, 'T2': T2, 'T3': T3, 'T4': T4, 'T5': T5},
                }
            patient.last_collected_at = now
    except AccessError as error:
        return jsonify(Response.error(error.status_code, error.code)), error.status_code

    return jsonify(Response.success(data=result, msg="数据上传成功"))
