"""Persistent management identities and fail-closed clinical scope fences."""
import json
from config import db


class ManagementPreview(db.Model):
    __tablename__ = 'data_management_preview'
    id = db.Column(db.String(36), primary_key=True)
    actor_id = db.Column(db.Integer, nullable=False)
    scope_json = db.Column(db.Text, nullable=False)
    inventory_json = db.Column(db.Text, nullable=False)
    scope_hash = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)


class ManagementOperation(db.Model):
    __tablename__ = 'data_management_operation'
    id = db.Column(db.String(36), primary_key=True)
    request_id = db.Column(db.String(36), nullable=False)
    preview_id = db.Column(db.String(36), nullable=False)
    actor_id = db.Column(db.Integer, nullable=False)
    owner_id = db.Column(db.Integer, nullable=False)
    patient_id = db.Column(db.Integer, nullable=False, index=True)
    kind = db.Column(db.String(32), nullable=False)
    record_id = db.Column(db.String(128))
    scope_json = db.Column(db.Text, nullable=False)
    scope_hash = db.Column(db.String(64), nullable=False)
    inventory_json = db.Column(db.Text, nullable=False)
    counts_json = db.Column(db.Text, nullable=False)
    trace_id = db.Column(db.String(36), nullable=False)
    stage = db.Column(db.String(32), nullable=False)
    state = db.Column(db.String(32), nullable=False)
    error_code = db.Column(db.String(64))
    discard_pending = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (db.UniqueConstraint('actor_id', 'request_id', name='uq_management_request'),)


class ManagementItem(db.Model):
    __tablename__ = 'data_management_item'
    operation_id = db.Column(db.String(36), db.ForeignKey('data_management_operation.id'), primary_key=True)
    table_name = db.Column(db.String(64), primary_key=True)
    row_id = db.Column(db.String(128), primary_key=True)
    __table_args__ = (db.Index('ix_management_item_identity', 'table_name', 'row_id'),)


class ManagementAuditBridge(db.Model):
    """Hash-only links keep surviving patient audit events verifiable after excision."""
    __tablename__ = 'data_management_audit_bridge'
    event_hash = db.Column(db.String(64), primary_key=True)
    previous_event_hash = db.Column(db.String(64))
    operation_id = db.Column(db.String(36), nullable=False)


def visible_patient(patient_id):
    """Patient-wide operations hide only the targeted patient from directories."""
    return ~db.exists().where(
        ManagementOperation.patient_id == patient_id, ManagementOperation.kind == 'patient')


def assert_clinical_scope(session, patient_id, *, record_id=None, capture_id=None):
    from access import AccessError
    query = session.query(ManagementOperation).filter_by(patient_id=patient_id)
    live = query.filter(ManagementOperation.stage != 'completed').first()
    if live is not None:
        raise AccessError(409, 'scope_fenced')
    if query.filter_by(kind='patient', stage='completed').first() is not None:
        raise AccessError(410, 'scope_deleted')
    record_id = capture_id or record_id
    if record_id is not None:
        if query.filter_by(record_id=record_id, stage='completed').first() is not None:
            raise AccessError(410, 'scope_deleted')


def assert_capture_id_available(session, capture_id):
    from access import AccessError
    operation = session.query(ManagementOperation).filter_by(kind='capture', record_id=capture_id).first()
    if operation is None:
        # Whole-patient receipts retain precisely these capture UUIDs after purge.
        operation = (session.query(ManagementOperation).join(ManagementItem)
                     .filter(ManagementOperation.kind == 'patient',
                             ManagementItem.table_name == 'collection_sessions',
                             ManagementItem.row_id == capture_id).first())
    if operation is not None:
        raise AccessError(410 if operation.stage == 'completed' else 409,
                          'scope_deleted' if operation.stage == 'completed' else 'scope_fenced')


def frozen_inventory(operation):
    return json.loads(operation.inventory_json)
