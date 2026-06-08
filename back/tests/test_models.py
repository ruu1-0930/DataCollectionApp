from models.models import Clinician, Device, Patient, PatientPII, DeviceRawData, DeviceTransformedData


def test_clinician_patient_pii_chain(db):
    c = Clinician(hospital='H', dept='D', name='Dr', phone='13800000000',
                  terminal_code='term-1', passcode_hash='x')
    db.session.add(c); db.session.commit()

    p = Patient(clinician_id=c.id, subject_id='#00001', gender='F', age=30)
    db.session.add(p); db.session.commit()

    pii = PatientPII(patient_id=p.id, name='张三', phone='13900000000')
    db.session.add(pii); db.session.commit()

    assert p.clinician_id == c.id
    assert pii.patient_id == p.id
    # 关系可回查
    assert c.patients[0].subject_id == '#00001'


def test_raw_and_transformed_attribution(db):
    c = Clinician(hospital='H', dept='D', name='Dr', phone='1', terminal_code='t', passcode_hash='x')
    db.session.add(c); db.session.commit()
    dev = Device(device_code='DEV1', device_name='insole', clinician_id=c.id)
    p = Patient(clinician_id=c.id, subject_id='#00002')
    db.session.add_all([dev, p]); db.session.commit()

    raw = DeviceRawData(device_id=dev.id, patient_id=p.id, clinician_id=c.id,
                        foot='L', p1=1, p2=2, p3=3, p4=4, p5=5, p6=6, p7=7, p8=8, p9=9,
                        ax=1, ay=2, az=3, gx=4, gy=5, gz=6,
                        step_length=1, walking_speed=2,
                        single_support_time=3, double_support_time=4)
    db.session.add(raw); db.session.commit()
    tr = DeviceTransformedData(raw_data_id=raw.id, T1=0.1, T2=0.2, T3=0.3, T4=0.4, T5=0.5)
    db.session.add(tr); db.session.commit()

    assert raw.clinician_id == c.id and raw.patient_id == p.id and raw.device_id == dev.id
    assert tr.raw_data_id == raw.id
