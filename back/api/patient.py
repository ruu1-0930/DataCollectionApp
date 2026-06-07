from flask import Blueprint, request, jsonify, g
from config import db
from models.models import Patient, PatientPII, DeviceRawData, DeviceTransformedData
from utils import Response, token_required

patient_bp = Blueprint('patient', __name__)


def format_subject_id(n: int) -> str:
    return '#%05d' % n
