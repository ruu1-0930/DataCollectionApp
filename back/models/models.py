from config import db
import datetime


class Clinician(db.Model):
    __tablename__ = 'clinicians'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hospital = db.Column(db.String(100), nullable=False)
    dept = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    terminal_code = db.Column(db.String(100), nullable=False)
    passcode_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('phone', 'terminal_code', name='uq_clinician_phone_terminal'),
    )


class Device(db.Model):
    __tablename__ = 'devices'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_code = db.Column(db.String(50), unique=True, nullable=False)
    device_name = db.Column(db.String(100))
    is_enabled = db.Column(db.Boolean, default=True)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    clinician = db.relationship('Clinician', backref='devices')


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    subject_id = db.Column(db.String(20), unique=True, nullable=False)
    gender = db.Column(db.String(10))
    age = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_collected_at = db.Column(db.DateTime)

    clinician = db.relationship('Clinician', backref='patients')


class PatientPII(db.Model):
    __tablename__ = 'patient_pii'
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100))
    address = db.Column(db.String(255))

    patient = db.relationship('Patient', backref=db.backref('pii', uselist=False))


class DeviceRawData(db.Model):
    __tablename__ = 'device_raw_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False, index=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    clinician_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False, index=True)
    # scope A：暂存 6 维，38 维扩展见后续 spec
    ax = db.Column(db.Float, nullable=False)
    ay = db.Column(db.Float, nullable=False)
    az = db.Column(db.Float, nullable=False)
    gx = db.Column(db.Float, nullable=False)
    gy = db.Column(db.Float, nullable=False)
    gz = db.Column(db.Float, nullable=False)
    collected_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    uploaded_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    # 复合索引支撑按患者历史的时间范围分页查询，与 SQL idx_raw_patient_collected 一致
    __table_args__ = (
        db.Index('idx_raw_patient_collected', 'patient_id', 'collected_at'),
    )

    device = db.relationship('Device', backref='raw_data')
    patient = db.relationship('Patient', backref='raw_data')


class DeviceTransformedData(db.Model):
    __tablename__ = 'device_transformed_data'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    raw_data_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False, index=True)
    T1 = db.Column(db.Float, nullable=False)
    T2 = db.Column(db.Float, nullable=False)
    T3 = db.Column(db.Float, nullable=False)
    T4 = db.Column(db.Float, nullable=False)
    T5 = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    raw_data = db.relationship('DeviceRawData', backref=db.backref('transformed_data', uselist=False))
