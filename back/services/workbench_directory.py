"""Small joined, paginated projections for the shared clinical selector."""

from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from access import AccessError, load_account_context, require_capability
from config import db
from models.models import Clinician, Patient, PatientPII


class DirectoryQueryError(ValueError):
    pass


@lru_cache(maxsize=2)
def _validator(name):
    path = Path(__file__).resolve().parents[1] / 'contracts/workbench_directory_v1.schema.json'
    schema = json.loads(path.read_text(encoding='utf-8'))
    return Draft202012Validator({'$schema': schema['$schema'], '$defs': schema['$defs'],
                                '$ref': '#/$defs/' + name})


def _options(hospital, q, page, page_size):
    if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
        raise DirectoryQueryError('invalid_directory_query')
    values = []
    for value in (hospital, q):
        if value is not None and (not isinstance(value, str) or len(value.strip()) > 100):
            raise DirectoryQueryError('invalid_directory_query')
        values.append(value.strip() or None if value is not None else None)
    return values


def _pattern(value):
    return '%' + value.replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'


def _doctor(row):
    return {key: getattr(row, key) for key in ('id', 'hospital', 'dept', 'name')}


def _page(query, *, page, page_size, serialize, schema):
    total = query.order_by(None).count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    result = dict(items=[serialize(row) for row in rows], total=total, page=page, page_size=page_size)
    _validator(schema).validate(result)
    return result


class WorkbenchDirectoryService:
    def __init__(self, engine=None):
        self.engine = db.engine if engine is None else engine

    def patients(self, account, *, hospital=None, clinician_id=None, q=None, page=1, page_size=50):
        hospital, q = _options(hospital, q, page, page_size)
        if clinician_id is not None and (type(clinician_id) is not int or clinician_id < 1):
            raise DirectoryQueryError('invalid_directory_query')
        with Session(self.engine, autoflush=False) as session:
            account = load_account_context(account.clinician_id, session=session)
            require_capability(account, 'clinical.read')
            if account.role == 'clinician' and clinician_id not in (None, account.clinician_id):
                raise AccessError(403, 'forbidden')
            query = session.query(Patient, Clinician, PatientPII).select_from(Patient).join(
                Clinician, Clinician.id == Patient.clinician_id).outerjoin(
                PatientPII, PatientPII.patient_id == Patient.id)
            if account.role == 'clinician':
                query = query.filter(Patient.clinician_id == account.clinician_id)
            if clinician_id is not None:
                query = query.filter(Patient.clinician_id == clinician_id)
            if hospital is not None:
                query = query.filter(Clinician.hospital == hospital)
            if q:
                pattern = _pattern(q)
                query = query.filter(or_(Patient.subject_id.like(pattern, escape='!'),
                                         PatientPII.name.like(pattern, escape='!')))

            def serialize(row):
                patient, owner, pii = row
                return dict(id=patient.id, subject_id=patient.subject_id, name=pii.name if pii else None,
                    gender=patient.gender, age=patient.age,
                    last_collected_at=patient.last_collected_at.isoformat() if patient.last_collected_at else None,
                    owner=_doctor(owner))

            return _page(query.order_by(Patient.id.desc()), page=page, page_size=page_size,
                         serialize=serialize, schema='WorkbenchPatientPage')

    def clinicians(self, account, *, hospital=None, q=None, page=1, page_size=50):
        hospital, q = _options(hospital, q, page, page_size)
        with Session(self.engine, autoflush=False) as session:
            account = load_account_context(account.clinician_id, session=session)
            require_capability(account, 'admin.read')
            query = session.query(Clinician)
            if hospital is not None:
                query = query.filter(Clinician.hospital == hospital)
            if q:
                query = query.filter(Clinician.name.like(_pattern(q), escape='!'))
            return _page(query.order_by(Clinician.id), page=page, page_size=page_size,
                         serialize=_doctor, schema='WorkbenchDoctorPage')
