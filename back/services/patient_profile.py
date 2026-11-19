"""Strict patient-profile V2 dictionaries; legacy patient routes remain separate."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Optional, TypedDict

from jsonschema import Draft202012Validator, ValidationError

from access import load_account_context, require_capability, require_patient_scope
from config import db
from models.models import Patient, PatientPII
from services.clinician_validation import PHONE_PATTERN
from services.collection_ingest import write_transaction
from services.data_management_scope import assert_clinical_scope


class _OptionalPhone(TypedDict, total=False):
    phone: Optional[str]


class PatientProfileInputV2(_OptionalPhone):
    name: str
    gender: str
    age: int
    height_cm: float
    weight_kg: float
    shoe_size_eu: float


class PatientProfileV2(TypedDict):
    id: int
    subject_id: str
    name: Optional[str]
    phone: Optional[str]
    gender: Optional[str]
    age: Optional[int]
    height_cm: Optional[float]
    weight_kg: Optional[float]
    shoe_size_eu: Optional[float]
    last_collected_at: Optional[str]
    existed: bool


class PatientProfileError(ValueError):
    def __init__(self, status_code=400):
        self.status_code = status_code
        super().__init__('patient_profile_rejected')


@lru_cache(maxsize=1)
def _input_validator():
    path = Path(__file__).resolve().parents[1] / 'contracts' / 'patient_profile_v2.schema.json'
    return Draft202012Validator(json.loads(path.read_text(encoding='utf-8')))


def normalize_profile(payload) -> PatientProfileInputV2:
    if not isinstance(payload, dict):
        raise PatientProfileError()
    value = dict(payload)
    if isinstance(value.get('name'), str):
        value['name'] = value['name'].strip()
    phone = value.get('phone')
    if phone is None or (isinstance(phone, str) and not phone.strip()):
        value['phone'] = None
    elif not isinstance(phone, str) or PHONE_PATTERN.fullmatch(phone) is None:
        raise PatientProfileError()
    try:
        # JSON Schema numeric comparisons alone do not reject every NaN value.
        json.dumps(value, allow_nan=False)
        _input_validator().validate(value)
    except (TypeError, ValueError, ValidationError):
        raise PatientProfileError() from None
    if type(value['age']) is not int:
        raise PatientProfileError()
    return value


def _public(patient, *, existed=False) -> PatientProfileV2:
    pii = patient.pii
    return {
        'id': patient.id, 'subject_id': patient.subject_id,
        'name': pii.name if pii else None, 'phone': pii.phone if pii else None,
        'gender': patient.gender, 'age': patient.age,
        'height_cm': patient.height_cm, 'weight_kg': patient.weight_kg,
        'shoe_size_eu': patient.shoe_size_eu,
        'last_collected_at': patient.last_collected_at.isoformat() if patient.last_collected_at else None,
        'existed': existed,
    }


class PatientProfileService:
    """Save current profiles without creating or modifying collection registrations."""

    def _actor(self, actor, capability, *, session=None):
        account = load_account_context(actor.clinician_id, session=session)
        require_capability(account, capability)
        return account

    def _patient(self, actor, patient_id, capability, *, session, lock=False):
        account = self._actor(actor, capability, session=session)
        query = session.query(Patient).filter_by(id=patient_id)
        patient = (query.with_for_update() if lock else query).one_or_none()
        if patient is None:
            if lock:
                assert_clinical_scope(session, patient_id)
            raise PatientProfileError(404)
        require_patient_scope(account, owner_id=patient.clinician_id, capability=capability)
        assert_clinical_scope(session, patient.id)
        return patient

    def create(self, actor, payload) -> PatientProfileV2:
        account = self._actor(actor, 'clinician.write')
        value = normalize_profile(payload)
        if value['phone'] is not None:
            duplicate = (db.session.query(Patient).join(PatientPII, PatientPII.patient_id == Patient.id)
                .filter(Patient.clinician_id == account.clinician_id, PatientPII.phone == value['phone']).first())
            if duplicate is not None:
                assert_clinical_scope(db.session, duplicate.id)
                return _public(duplicate, existed=True)
        patient = Patient(clinician_id=account.clinician_id, subject_id='pending',
                          **{key: value[key] for key in ('gender', 'age', 'height_cm', 'weight_kg', 'shoe_size_eu')})
        db.session.add(patient)
        db.session.flush()
        patient.subject_id = '#%05d' % patient.id
        patient.pii = PatientPII(name=value['name'], phone=value['phone'])
        db.session.commit()
        return _public(patient)

    def update(self, actor, patient_id, payload) -> PatientProfileV2:
        with write_transaction() as session:
            patient = self._patient(actor, patient_id, 'data.manage', session=session, lock=True)
            value = normalize_profile(payload)
            for key in ('gender', 'age', 'height_cm', 'weight_kg', 'shoe_size_eu'):
                setattr(patient, key, value[key])
            if patient.pii is None:
                patient.pii = PatientPII(name=value['name'], phone=value['phone'])
            else:
                patient.pii.name, patient.pii.phone = value['name'], value['phone']
            return _public(patient)

    def get(self, actor, patient_id) -> PatientProfileV2:
        return _public(self._patient(actor, patient_id, 'clinical.read', session=db.session))
