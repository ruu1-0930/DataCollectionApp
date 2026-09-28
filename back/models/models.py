from config import db
import datetime
from sqlalchemy import DDL, event
from sqlalchemy.dialects import mysql


class Clinician(db.Model):
    __tablename__ = 'clinicians'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    hospital = db.Column(db.String(100), nullable=False)
    dept = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    passcode_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('hospital', 'phone', name='uq_clinician_hospital_phone'),
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
    # 一行 = 一只脚的一帧，与硬件原始导出（每行带 L/R 标记）一致
    foot = db.Column(db.String(1), nullable=False)  # 'L' / 'R'
    # 压力 1-9（原始导出 C-K 列）
    p1 = db.Column(db.Float, nullable=False)
    p2 = db.Column(db.Float, nullable=False)
    p3 = db.Column(db.Float, nullable=False)
    p4 = db.Column(db.Float, nullable=False)
    p5 = db.Column(db.Float, nullable=False)
    p6 = db.Column(db.Float, nullable=False)
    p7 = db.Column(db.Float, nullable=False)
    p8 = db.Column(db.Float, nullable=False)
    p9 = db.Column(db.Float, nullable=False)
    # 加速度/IMU 10-15（原始导出 L-Q 列）
    ax = db.Column(db.Float, nullable=False)
    ay = db.Column(db.Float, nullable=False)
    az = db.Column(db.Float, nullable=False)
    gx = db.Column(db.Float, nullable=False)
    gy = db.Column(db.Float, nullable=False)
    gz = db.Column(db.Float, nullable=False)
    # 步态 16-19（原始导出 R-U 列）
    step_length = db.Column(db.Float, nullable=False)
    walking_speed = db.Column(db.Float, nullable=False)
    single_support_time = db.Column(db.Float, nullable=False)
    double_support_time = db.Column(db.Float, nullable=False)
    # collected_at = 服务器接收/入库时刻（BLE 帧不含设备时间戳，故非设备 Col A 采样时刻）；
    # 同一帧拆出的 L/R 两行共享该时刻用于配对。uploaded_at 同为落库时刻。
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


# ASCII/binary identity fields keep the six-part key within MySQL 5.7 index limits.
# Payload text remains UTF-8; it is not a mutable JSON column or a clinical Float.
def _identity(length):
    return db.String(length).with_variant(
        mysql.VARCHAR(length, charset='ascii', collation='ascii_bin'), 'mysql')


_canonical = db.Text().with_variant(mysql.LONGTEXT(collation='utf8mb4_bin'), 'mysql')
_utc_time = db.DateTime().with_variant(mysql.DATETIME(fsp=3), 'mysql')
_source_time = db.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql')


def _state(name, *values):
    # Native MySQL ENUM; SQLite receives an actual CHECK, including bulk SQL writes.
    return db.Enum(*values, name=name, native_enum=True, create_constraint=True,
                   validate_strings=True)


class GaitSessionRevision(db.Model):
    __tablename__ = 'gait_session_revision'
    id = db.Column(_identity(36), primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    device_id = db.Column(db.Integer, db.ForeignKey('devices.id'), nullable=False)
    session_key = db.Column(_identity(128), nullable=False)
    revision = db.Column(db.Integer, nullable=False)
    state = db.Column(_state('session_revision_state', 'collecting', 'closed_by_inactivity', 'superseded'), nullable=False)
    ordered_row_ids_canonical = db.Column(_canonical, nullable=False)
    first_row_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False)
    last_row_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False)
    row_count = db.Column(db.Integer, nullable=False)
    last_accepted_row_id = db.Column(db.Integer, db.ForeignKey('device_raw_data.id'), nullable=False)
    event_start_at = db.Column(_source_time, nullable=False)
    event_end_at = db.Column(_source_time, nullable=False)
    ingest_start_at = db.Column(_source_time, nullable=False)
    ingest_end_at = db.Column(_source_time, nullable=False)
    closure_policy_version = db.Column(_identity(64), nullable=False)
    closure_evidence_canonical = db.Column(_canonical)
    closed_at = db.Column(_utc_time)
    superseded_by_revision_id = db.Column(_identity(36), db.ForeignKey('gait_session_revision.id'))
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    __table_args__ = (
        db.UniqueConstraint('patient_id', 'session_key', 'revision', name='uq_session_revision'),
        db.CheckConstraint('revision >= 1 AND row_count >= 1', name='ck_revision_positive'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class SnapshotBuildAttempt(db.Model):
    __tablename__ = 'snapshot_build_attempt'
    id = db.Column(_identity(36), primary_key=True)
    identity_fingerprint = db.Column(_identity(64), nullable=False)
    attempt_number = db.Column(db.Integer, nullable=False)
    state = db.Column(_state('snapshot_build_state', 'pending', 'running', 'succeeded', 'failed'), nullable=False)
    error_code = db.Column(_identity(64))
    error_message = db.Column(db.String(256))  # safe operational text, never PHI
    trace_id = db.Column(_identity(36), nullable=False)
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    started_at = db.Column(_utc_time)
    finished_at = db.Column(_utc_time)
    __table_args__ = (
        db.UniqueConstraint('identity_fingerprint', 'attempt_number', name='uq_build_attempt_number'),
        db.CheckConstraint('attempt_number >= 1', name='ck_attempt_positive'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class AnalysisSnapshot(db.Model):
    __tablename__ = 'analysis_snapshot'
    id = db.Column(_identity(36), primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    session_revision_id = db.Column(_identity(36), db.ForeignKey('gait_session_revision.id'), nullable=False)
    raw_data_fingerprint = db.Column(_identity(64), nullable=False)
    identity_fingerprint = db.Column(_identity(64), nullable=False, unique=True)
    snapshot_schema_version = db.Column(_identity(32), nullable=False)
    analyzer_set_version = db.Column(_identity(64), nullable=False)
    threshold_profile_version = db.Column(_identity(64), nullable=False)
    canonical_payload = db.Column(_canonical, nullable=False)
    content_hash = db.Column(_identity(64), nullable=False)
    state = db.Column(_state('analysis_snapshot_state', 'published', 'superseded'), nullable=False)
    state_version = db.Column(db.Integer, nullable=False)
    superseded_by_snapshot_id = db.Column(_identity(36), db.ForeignKey('analysis_snapshot.id'))
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    published_at = db.Column(_utc_time, nullable=False)
    superseded_at = db.Column(_utc_time)
    __table_args__ = (
        db.UniqueConstraint('patient_id', 'session_revision_id', 'raw_data_fingerprint',
            'snapshot_schema_version', 'analyzer_set_version', 'threshold_profile_version',
            name='uq_snapshot_identity'),
        db.CheckConstraint('state_version >= 1', name='ck_snapshot_state_version'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class AgentSnapshotProjection(db.Model):
    __tablename__ = 'agent_snapshot_projection'
    snapshot_id = db.Column(_identity(36), db.ForeignKey('analysis_snapshot.id'), primary_key=True)
    projection_schema_version = db.Column(_identity(32), primary_key=True)
    canonical_payload = db.Column(_canonical, nullable=False)
    content_hash = db.Column(_identity(64), nullable=False)
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    __table_args__ = ({'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},)


class SnapshotPublicationClaim(db.Model):
    __tablename__ = 'snapshot_publication_claim'
    id = db.Column(_identity(36), primary_key=True)
    snapshot_id = db.Column(_identity(36), db.ForeignKey('analysis_snapshot.id'), nullable=False)
    state_version = db.Column(db.Integer, nullable=False)
    workflow_run_id = db.Column(_identity(36), nullable=False)  # belongs to another service; no cross-DB FK
    candidate_hash = db.Column(_identity(64), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False)
    claimed_at = db.Column(_utc_time, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('snapshot_id', 'state_version', 'workflow_run_id', 'candidate_hash',
                            name='uq_snapshot_claim'),
        db.CheckConstraint('state_version >= 1', name='ck_claim_state_version'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},
    )


class ClinicalAuditEvent(db.Model):
    __tablename__ = 'clinical_audit_event'
    id = db.Column(_identity(36), primary_key=True)
    trace_id = db.Column(_identity(36), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('clinicians.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    session_revision_id = db.Column(_identity(36), db.ForeignKey('gait_session_revision.id'))
    snapshot_id = db.Column(_identity(36), db.ForeignKey('analysis_snapshot.id'))
    action = db.Column(_identity(64), nullable=False)
    result = db.Column(_identity(64), nullable=False)
    canonical_payload = db.Column(_canonical, nullable=False)
    event_hash = db.Column(_identity(64), nullable=False)
    previous_event_hash = db.Column(_identity(64))
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    __table_args__ = ({'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4'},)


class IntegrationOutbox(db.Model):
    __tablename__ = 'integration_outbox'
    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True, autoincrement=True)
    event_type = db.Column(_identity(64), nullable=False)
    event_version = db.Column(_identity(32), nullable=False)
    snapshot_id = db.Column(_identity(36), db.ForeignKey('analysis_snapshot.id'), nullable=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    state_version = db.Column(db.Integer, nullable=False)
    canonical_payload = db.Column(_canonical, nullable=False)
    content_hash = db.Column(_identity(64), nullable=False)
    created_at = db.Column(_utc_time, nullable=False, default=datetime.datetime.utcnow)
    published_at = db.Column(_utc_time)
    __table_args__ = (
        db.CheckConstraint('state_version >= 1', name='ck_outbox_state_version'),
        {'mysql_engine': 'InnoDB', 'mysql_charset': 'utf8mb4', 'sqlite_autoincrement': True},
    )


# Database triggers cover Core/bulk SQL too. They protect content, not publication
# transactions: repositories/services must later coordinate snapshot/audit/outbox.
_IMMUTABLE_FIELDS = {
    AnalysisSnapshot: ('id', 'patient_id', 'session_revision_id', 'raw_data_fingerprint',
        'identity_fingerprint', 'snapshot_schema_version', 'analyzer_set_version',
        'threshold_profile_version', 'canonical_payload', 'content_hash', 'created_at', 'published_at'),
    AgentSnapshotProjection: ('snapshot_id', 'projection_schema_version', 'canonical_payload', 'content_hash', 'created_at'),
    SnapshotPublicationClaim: tuple(c.name for c in SnapshotPublicationClaim.__table__.columns),
    IntegrationOutbox: ('id', 'event_type', 'event_version', 'snapshot_id', 'patient_id',
        'state_version', 'canonical_payload', 'content_hash', 'created_at'),
}


def _install_trigger(model, name, operation, sqlite_body, mysql_body):
    table = model.__table__
    for dialect, body in [('sqlite', sqlite_body), ('mysql', mysql_body)]:
        event.listen(table, 'after_create', DDL(
            f'CREATE TRIGGER {name} BEFORE {operation} ON {table.name} '
            f'FOR EACH ROW {body}').execute_if(dialect=dialect))


for _model, _fields in _IMMUTABLE_FIELDS.items():
    _sqlite_condition = ' OR '.join(f'NEW.{field} IS NOT OLD.{field}' for field in _fields)
    # MySQL collation equality may ignore case and trailing spaces, including on
    # utf8mb4_bin TEXT. BINARY compares the persisted bytes of frozen content.
    _mysql_condition = ' OR '.join(f'NOT (BINARY NEW.{field} <=> BINARY OLD.{field})' for field in _fields)
    if _model is AnalysisSnapshot:
        _sqlite_condition += ' OR NEW.state_version < OLD.state_version OR (NEW.state IS NOT OLD.state AND NEW.state_version <= OLD.state_version)'
        _mysql_condition += ' OR NEW.state_version < OLD.state_version OR (NEW.state <> OLD.state AND NEW.state_version <= OLD.state_version)'
    _install_trigger(_model, 'trg_' + _model.__tablename__ + '_immutable', 'UPDATE',
        f"WHEN {_sqlite_condition} BEGIN SELECT RAISE(ABORT, 'immutable content or state version'); END",
        f"BEGIN IF {_mysql_condition} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'immutable content or state version'; END IF; END")


_POSITIVE_FIELDS = {
    GaitSessionRevision: ('revision', 'row_count'),
    SnapshotBuildAttempt: ('attempt_number',),
    AnalysisSnapshot: ('state_version',),
    SnapshotPublicationClaim: ('state_version',),
    IntegrationOutbox: ('state_version',),
}
for _model, _fields in _POSITIVE_FIELDS.items():
    _condition = ' OR '.join(f'NEW.{field} < 1' for field in _fields)
    for _operation in ('INSERT', 'UPDATE'):
        _install_trigger(_model, f'trg_{_model.__tablename__}_positive_{_operation.lower()}',
            _operation,
            f"WHEN {_condition} BEGIN SELECT RAISE(ABORT, 'positive values required'); END",
            f"BEGIN IF {_condition} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'positive values required'; END IF; END")

for _operation in ('UPDATE', 'DELETE'):
    _install_trigger(ClinicalAuditEvent, 'trg_clinical_audit_event_no_' + _operation.lower(), _operation,
        "BEGIN SELECT RAISE(ABORT, 'append-only clinical audit'); END",
        "BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'append-only clinical audit'; END")
