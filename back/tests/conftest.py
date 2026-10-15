import os
import sys
import pytest

# 让 tests 能 import 到 back 根下的 config/app/models
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import create_app, db as _db


@pytest.fixture
def app():
    test_config = {
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'SECRET_KEY': 'test-secret',
        'TESTING': True,
    }
    app = create_app(test_config)
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def admin_scope(client, db):
    from models.models import Clinician
    result = {}
    for index, key in enumerate(('doctor_a', 'doctor_b', 'admin')):
        credentials = {'hospital': f'synthetic-hospital-{index}', 'dept': 'synthetic',
                       'name': f'synthetic-{key}', 'phone': f'1380000000{index}',
                       'passcode': 'synthetic-passcode'}
        response = client.post('/clinician/enable', json=credentials)
        assert response.status_code == 200
        data = response.get_json()['data']
        result[key] = {'id': data['clinician']['id'], 'credentials': credentials,
                       'headers': {'Authorization': 'Bearer ' + data['token']}}
    db.session.get(Clinician, result['admin']['id']).role = 'admin_readonly'
    db.session.commit()
    return result


@pytest.fixture
def admin_data(admin_scope, db):
    from datetime import datetime, timezone
    from models.models import Patient, PatientPII, Device, DeviceRawData, DeviceTransformedData
    from services.analysis_snapshot import AnalysisSnapshotService
    from services.gait_session_revision import _session_id
    at = datetime(2026, 9, 29, 0, 30)
    patients, devices, rows = [], [], []
    for index, key in enumerate(('doctor_a', 'doctor_b')):
        actor = admin_scope[key]['id']
        patient = Patient(clinician_id=actor, subject_id=f'#admin-{index}', age=60, gender='F')
        device = Device(clinician_id=actor, device_code=f'synthetic-admin-device-{index}')
        db.session.add_all([patient, device])
        db.session.flush()
        db.session.add(PatientPII(patient_id=patient.id, name=f'synthetic-patient-{index}',
                                  phone=f'1390000000{index}', email=None, address=None))
        patients.append(patient.id)
        devices.append(device.id)
        for row_index in range(4 if index == 0 else 1):
            row = DeviceRawData(clinician_id=actor, patient_id=patient.id, device_id=device.id,
                foot='L' if row_index % 2 == 0 else 'R', collected_at=at, uploaded_at=at,
                **{f'p{i}': 100.0 for i in range(1, 10)}, ax=1, ay=2, az=3, gx=4, gy=5, gz=6,
                step_length=.6, walking_speed=1.2, single_support_time=.4, double_support_time=.2)
            db.session.add(row)
            db.session.flush()
            rows.append(row.id)
    db.session.add(DeviceTransformedData(raw_data_id=rows[0], T1=.1, T2=.2, T3=.3, T4=.4, T5=.5))
    db.session.commit()
    session_id = _session_id(patients[0], at)
    created = AnalysisSnapshotService(clock=lambda: datetime(2026, 10, 15, tzinfo=timezone.utc)).ensure_snapshot(
        actor_id=admin_scope['doctor_a']['id'], patient_id=patients[0], session_id=session_id)
    return {'patient_id': patients[0], 'other_patient_id': patients[1], 'device_id': devices[0],
            'other_device_id': devices[1], 'raw_ids': rows[:4], 'session_id': session_id,
            'snapshot_id': str(created.snapshot_id)}
