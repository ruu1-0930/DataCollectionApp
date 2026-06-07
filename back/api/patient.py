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
