from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Patient, PatientPII, DeviceRawData, DeviceTransformedData
from utils import Response, token_required

patient_bp = Blueprint('patient', __name__)


def format_subject_id(n: int) -> str:
    return '#%05d' % n


def _patient_public(p, existed=False):
    pii = p.pii
    return {
        'id': p.id, 'subject_id': p.subject_id,
        'gender': p.gender, 'age': p.age,
        'name': pii.name if pii else None,
        'phone': pii.phone if pii else None,
        'last_collected_at': p.last_collected_at.isoformat() if p.last_collected_at else None,
        'existed': existed,
    }


@patient_bp.route('/patients', methods=['POST'])
@token_required()
def create_patient():
    data = request.json or {}
    name = data.get('name')
    phone = data.get('phone')
    if not name or not phone:
        return jsonify(Response.error(400, "姓名与手机号为必填")), 400

    dup = (db.session.query(Patient).join(PatientPII, PatientPII.patient_id == Patient.id)
           .filter(Patient.clinician_id == g.clinician_id, PatientPII.phone == phone).first())
    if dup:
        return jsonify(Response.success(data=_patient_public(dup, existed=True), msg="患者已存在"))

    p = Patient(clinician_id=g.clinician_id, subject_id='pending',
                gender=data.get('gender'), age=data.get('age'))
    db.session.add(p)
    db.session.flush()
    p.subject_id = format_subject_id(p.id)
    db.session.add(PatientPII(patient_id=p.id, name=name, phone=phone,
                              email=data.get('email'), address=data.get('address')))
    db.session.commit()
    return jsonify(Response.success(data=_patient_public(p), msg="新建患者成功"))


@patient_bp.route('/patients', methods=['GET'])
@token_required()
def list_patients():
    patients = (Patient.query.filter_by(clinician_id=g.clinician_id)
                .order_by(Patient.created_at.desc()).all())
    return jsonify(Response.success(data=[_patient_public(p) for p in patients]))


@patient_bp.route('/patients/<int:patient_id>', methods=['GET'])
@token_required()
def get_patient(patient_id):
    p = Patient.query.get(patient_id)
    if not p:
        return jsonify(Response.error(404, "患者不存在")), 404
    if p.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权访问该患者")), 403
    return jsonify(Response.success(data=_patient_public(p)))


@patient_bp.route('/patients/<int:patient_id>/data', methods=['GET'])
@token_required()
def patient_history(patient_id):
    p = Patient.query.get(patient_id)
    if not p:
        return jsonify(Response.error(404, "患者不存在")), 404
    if p.clinician_id != g.clinician_id:
        return jsonify(Response.error(403, "无权访问该患者")), 403

    q = (db.session.query(DeviceRawData, DeviceTransformedData)
         .outerjoin(DeviceTransformedData,
                    DeviceRawData.id == DeviceTransformedData.raw_data_id)
         .filter(DeviceRawData.patient_id == patient_id))

    start = request.args.get('start')
    end = request.args.get('end')
    if start:
        q = q.filter(DeviceRawData.collected_at >= start)
    if end:
        q = q.filter(DeviceRawData.collected_at <= end)

    total = q.count()
    page = max(int(request.args.get('page', 1)), 1)
    page_size = min(max(int(request.args.get('page_size', 50)), 1), 500)
    rows = (q.order_by(DeviceRawData.collected_at.desc())
            .offset((page - 1) * page_size).limit(page_size).all())

    items = []
    for raw, tr in rows:
        items.append({
            'id': raw.id,
            'foot': raw.foot,
            'collected_at': raw.collected_at.isoformat() if raw.collected_at else None,
            'p1': raw.p1, 'p2': raw.p2, 'p3': raw.p3, 'p4': raw.p4, 'p5': raw.p5,
            'p6': raw.p6, 'p7': raw.p7, 'p8': raw.p8, 'p9': raw.p9,
            'ax': raw.ax, 'ay': raw.ay, 'az': raw.az,
            'gx': raw.gx, 'gy': raw.gy, 'gz': raw.gz,
            'step_length': raw.step_length, 'walking_speed': raw.walking_speed,
            'single_support_time': raw.single_support_time,
            'double_support_time': raw.double_support_time,
            'transformed': ({'T1': tr.T1, 'T2': tr.T2, 'T3': tr.T3, 'T4': tr.T4, 'T5': tr.T5}
                            if tr else None),
        })
    return jsonify(Response.success(
        data={'items': items, 'total': total, 'page': page, 'page_size': page_size}))
