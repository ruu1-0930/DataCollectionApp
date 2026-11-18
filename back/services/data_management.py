"""Resumable capture deletion. Each local transaction commits before any HTTP call."""
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import json
from uuid import uuid4
from jsonschema import Draft202012Validator
from access import AccessError, load_account_context, require_patient_scope
from models.models import (Patient, CollectionSession, CollectionInsoleFrame, CollectionGpsRaw,
    CollectionRadarRaw, CollectionRadarTarget, DeviceRawData, DeviceTransformedData,
    GaitSessionRevision, AnalysisSnapshot, AgentSnapshotProjection, SnapshotPublicationClaim,
    SnapshotBuildAttempt, ClinicalAuditEvent, IntegrationOutbox)
from services.canonical_json import canonical_json_bytes, sha256_hex
from services.collection_ingest import write_transaction
from services.collection_records import _source, _LegacySource, _raw_base, raw_has_capture
from services.collection_verification import verification_for_capture
from services.data_management_scope import (ManagementPreview, ManagementOperation, ManagementItem,
    ManagementAuditBridge, frozen_inventory, assert_clinical_scope)
from services.agent_data_management_client import AgentDataManagementClient, AgentManagementError


class ManagementError(AccessError):
    pass


@lru_cache(maxsize=1)
def _schemas():
    return json.loads((Path(__file__).resolve().parents[1] / 'contracts/data_management_v1.schema.json').read_text(encoding='utf-8'))['contracts']


def validate(name, value):
    try:
        Draft202012Validator(_schemas()[name]).validate(value)
    except Exception:
        raise ManagementError(400, 'invalid_request') from None
    return value


def _json(value):
    return canonical_json_bytes(value).decode()


def _scope(session, actor, scope, *, lock=True):
    validate('ManagementScopeV1', scope)
    if scope['kind'] == 'patient':
        raise ManagementError(501, 'patient_scope_not_supported')
    account = load_account_context(actor.clinician_id, session=session)
    query = session.query(Patient).filter_by(id=scope['patient_id'])
    patient = (query.with_for_update() if lock else query).one_or_none()
    if patient is None:
        raise ManagementError(404, 'patient_not_found')
    require_patient_scope(account, owner_id=patient.clinician_id, capability='data.manage')
    return account, patient


def _inventory(session, actor, scope):
    account, patient = _scope(session, actor, scope)
    assert_clinical_scope(session, patient.id, record_id=scope['record_id'])
    source = _source(session, patient.id, patient.clinician_id if account.role != 'admin' else None, scope['record_id'])
    if (scope['kind'] == 'legacy_session') != isinstance(source, _LegacySource):
        raise ManagementError(400, 'scope_mismatch')
    ids = {}
    def selected(model, query):
        ids[model.__tablename__] = sorted(str(row[0]) for row in query)
    if isinstance(source, CollectionSession):
        if source.mobile_stopped_at is None or source.server_stopped_at is None:
            raise ManagementError(409, 'collection_in_progress')
        frames = session.query(CollectionInsoleFrame).filter_by(capture_id=source.capture_id).all()
        raw_ids = {v for frame in frames for v in (frame.left_raw_id, frame.right_raw_id)}
        version = verification_for_capture(session, source)
        source_versions = {source.capture_id: version['record_version']}
        pending = version['upload_state'] != 'verified'
        ids['collection_sessions'] = [source.capture_id]
        ids['collection_insole_frames'] = sorted(str(f.id) for f in frames)
        selected(CollectionGpsRaw, session.query(CollectionGpsRaw.id).filter_by(capture_id=source.capture_id))
        selected(CollectionRadarRaw, session.query(CollectionRadarRaw.id).filter_by(capture_id=source.capture_id))
    else:
        raw_ids = {row[0] for row in _raw_base(session, patient.id, (DeviceRawData.id,)).filter(
            DeviceRawData.collected_at.between(source.start, source.end), ~raw_has_capture())}
        source_versions, pending = {source.record_id: source.version}, False
    ids['device_raw_data'] = sorted(str(v) for v in raw_ids)
    selected(DeviceTransformedData, session.query(DeviceTransformedData.id).filter(DeviceTransformedData.raw_data_id.in_(raw_ids)))
    radar_ids = ids.get('collection_radar_raw', [])
    selected(CollectionRadarTarget, session.query(CollectionRadarTarget.id).filter(CollectionRadarTarget.parent_id.in_(radar_ids)))
    revisions = session.query(GaitSessionRevision).filter_by(patient_id=patient.id).all()
    affected = {r.id for r in revisions if raw_ids.intersection(json.loads(r.ordered_row_ids_canonical)) or r.session_key == 'C:' + scope['record_id']}
    # A reverse supersession FK is a real dependency, even if its payload uses other rows.
    while True:
        more = {r.id for r in revisions if r.superseded_by_revision_id in affected}
        if more <= affected:
            break
        affected |= more
    ids['gait_session_revision'] = sorted(affected)
    snapshots = session.query(AnalysisSnapshot).filter_by(patient_id=patient.id).all()
    snapshot_ids = {s.id for s in snapshots if s.session_revision_id in affected}
    while True:
        more = {s.id for s in snapshots if s.superseded_by_snapshot_id in snapshot_ids}
        if more <= snapshot_ids:
            break
        snapshot_ids |= more
    ids['analysis_snapshot'] = sorted(snapshot_ids)
    fingerprints = {s.identity_fingerprint for s in snapshots if s.id in snapshot_ids}
    attempts = session.query(SnapshotBuildAttempt).filter(SnapshotBuildAttempt.identity_fingerprint.in_(fingerprints)).all()
    # Builds can be reserved before a snapshot exists: inspect their audit-linked revision too.
    events = session.query(ClinicalAuditEvent).filter_by(patient_id=patient.id).all()
    traces = {e.trace_id for e in events if e.snapshot_id in snapshot_ids or e.session_revision_id in affected}
    attempts += session.query(SnapshotBuildAttempt).filter(SnapshotBuildAttempt.trace_id.in_(traces)).all()
    if any(a.state in {'pending', 'running'} for a in attempts):
        raise ManagementError(409, 'snapshot_building')
    ids['snapshot_build_attempt'] = sorted({a.id for a in attempts})
    ids['clinical_audit_event'] = sorted(e.id for e in events if e.trace_id in traces)
    selected(SnapshotPublicationClaim, session.query(SnapshotPublicationClaim.id).filter(SnapshotPublicationClaim.snapshot_id.in_(snapshot_ids)))
    selected(IntegrationOutbox, session.query(IntegrationOutbox.id).filter(IntegrationOutbox.snapshot_id.in_(snapshot_ids)))
    # Composite projection keys are represented by snapshot IDs and expanded server-side.
    ids['agent_snapshot_projection'] = sorted(snapshot_ids)
    sessions = sorted({r.session_key for r in revisions if r.id in affected} | ({'C:' + scope['record_id']} if scope['kind'] == 'capture' else {scope['record_id']}))
    extra = sorted(s.id for s in snapshots if s.id in snapshot_ids and s.session_revision_id in
                   {r.id for r in revisions if r.id in affected and set(json.loads(r.ordered_row_ids_canonical)) - raw_ids})
    counts = {name: len(values) for name, values in ids.items()}
    counts['agent_snapshot_projection'] = session.query(AgentSnapshotProjection).filter(AgentSnapshotProjection.snapshot_id.in_(snapshot_ids)).count()
    versions = dict(source_versions)
    versions.update({s.id: str(s.state_version) + ':' + s.content_hash for s in snapshots if s.id in snapshot_ids})
    return dict(items=ids, snapshot_ids=sorted(snapshot_ids), session_ids=sessions,
                source_versions=versions, counts=counts, extra_affected_results=extra, pending_upload=pending), patient


def _hash(scope, inventory):
    return sha256_hex(canonical_json_bytes([scope, inventory]))


def _preview_dto(preview):
    inventory = json.loads(preview.inventory_json)
    counts = dict(inventory['counts'])
    counts.update({'agent_' + k: v for k, v in inventory.get('agent_counts', {}).items()})
    return validate('DeletePreviewV1', dict(preview_id=preview.id, scope=json.loads(preview.scope_json),
        scope_hash=preview.scope_hash, source_versions=inventory['source_versions'], counts=counts,
        extra_affected_results=inventory['extra_affected_results'], pending_upload=inventory['pending_upload'],
        expires_at=preview.expires_at.isoformat(timespec='microseconds') + 'Z',
        snapshot_ids=inventory['snapshot_ids'], session_ids=inventory['session_ids'],
        agent_state=inventory.get('agent_state', 'pending'), agent_inventory_hash=inventory.get('agent_inventory_hash'),
        operation_id=inventory.get('operation_id')))


def get_delete_preview(actor, preview_id):
    with write_transaction() as session:
        preview = session.get(ManagementPreview, preview_id)
        if preview is None or preview.actor_id != actor.clinician_id or preview.expires_at <= datetime.utcnow():
            raise ManagementError(409, 'preview_expired')
        _scope(session, actor, json.loads(preview.scope_json))
        return _preview_dto(preview)


def _preview_payload(preview):
    return dict(schema_version=1, **{key: preview[key] for key in ('preview_id', 'scope_hash', 'scope', 'snapshot_ids', 'session_ids')})


def preview_delete(actor, scope, token=None, *, client=None):
    with write_transaction() as session:
        inventory, _ = _inventory(session, actor, scope)
        now = datetime.utcnow()
        preview = ManagementPreview(id=str(uuid4()), actor_id=actor.clinician_id, scope_json=_json(scope),
            inventory_json=_json(inventory), scope_hash=_hash(scope, inventory), expires_at=now + timedelta(minutes=10))
        session.add(preview)
        public = _preview_dto(preview)
    try:
        remote = (client or AgentDataManagementClient()).request('preview-inventory', _preview_payload(public), token)
        inventory.update(agent_counts=remote['counts'], agent_inventory_hash=remote['inventory_hash'],
                         agent_state='busy' if remote['busy'] else 'ready')
    except AgentManagementError:
        inventory.update(agent_state='unavailable', agent_inventory_hash=None)
    with write_transaction() as session:
        row = session.get(ManagementPreview, public['preview_id'])
        if row is None:
            raise ManagementError(409, 'preview_expired')
        row.inventory_json = _json(inventory)
        return _preview_dto(row)


def _authorized_operation(session, actor, operation_id):
    operation = session.query(ManagementOperation).filter_by(id=operation_id).with_for_update().one_or_none()
    if operation is None:
        raise ManagementError(404, 'operation_not_found')
    _scope(session, actor, json.loads(operation.scope_json))
    return operation


def _dto(operation):
    inventory = frozen_inventory(operation)
    return validate('ManagementOperationV1', dict(operation_id=operation.id, trace_id=operation.trace_id,
        scope=json.loads(operation.scope_json), scope_hash=operation.scope_hash, stage=operation.stage,
        state=operation.state, counts=json.loads(operation.counts_json), error_code=operation.error_code,
        snapshot_ids=inventory.get('snapshot_ids', []), session_ids=inventory.get('session_ids', []),
        expected_agent_inventory_hash=inventory['agent_inventory_hash'],
        agent_confirmation_required=operation.error_code == 'agent_reconfirmation_required'))


def begin_delete(actor, request, token=None, *, client=None):
    validate('DeleteRequestV1', request)
    # Return an existing request before touching an expired preview or making HTTP calls.
    with write_transaction() as session:
        existing = session.query(ManagementOperation).filter_by(actor_id=actor.clinician_id, request_id=request['request_id']).first()
        if existing:
            _authorized_operation(session, actor, existing.id)
            if (existing.preview_id, existing.discard_pending) != (request['preview_id'], request['discard_pending']):
                raise ManagementError(409, 'request_conflict')
            return _dto(existing)
    public = get_delete_preview(actor, request['preview_id'])
    if public['agent_state'] != 'ready':
        raise ManagementError(409 if public['agent_state'] == 'busy' else 503, 'agent_preview_not_ready')
    try:
        remote = (client or AgentDataManagementClient()).request('preview-inventory', _preview_payload(public), token)
    except AgentManagementError:
        raise ManagementError(503, 'agent_unavailable') from None
    if remote['busy'] or remote['inventory_hash'] != public['agent_inventory_hash']:
        raise ManagementError(409, 'agent_preview_stale')
    with write_transaction() as session:
        existing = session.query(ManagementOperation).filter_by(actor_id=actor.clinician_id, request_id=request['request_id']).first()
        if existing:
            _authorized_operation(session, actor, existing.id)
            if (existing.preview_id, existing.discard_pending) != (request['preview_id'], request['discard_pending']):
                raise ManagementError(409, 'request_conflict')
            return _dto(existing)
        preview = session.get(ManagementPreview, request['preview_id'])
        if preview is None or preview.actor_id != actor.clinician_id or preview.expires_at <= datetime.utcnow():
            raise ManagementError(409, 'preview_expired')
        scope = json.loads(preview.scope_json)
        inventory, patient = _inventory(session, actor, scope)
        if _hash(scope, inventory) != preview.scope_hash:
            raise ManagementError(409, 'preview_stale')
        if inventory['pending_upload'] and not request['discard_pending']:
            raise ManagementError(409, 'pending_upload_confirmation_required')
        inventory['agent_inventory_hash'] = remote['inventory_hash']
        inventory['counts'].update({'agent_' + k: v for k, v in remote['counts'].items()})
        if session.get(ManagementOperation, request['request_id']) is not None:
            raise ManagementError(409, 'request_conflict')
        operation = ManagementOperation(id=request['request_id'], request_id=request['request_id'], preview_id=preview.id,
            actor_id=actor.clinician_id, owner_id=patient.clinician_id, patient_id=patient.id,
            kind=scope['kind'], record_id=scope['record_id'], scope_json=_json(scope), scope_hash=preview.scope_hash,
            inventory_json=_json(inventory), counts_json=_json(inventory['counts']), trace_id=str(uuid4()),
            stage='fenced', state='running', discard_pending=request['discard_pending'], created_at=datetime.utcnow())
        session.add(operation)
        session.flush()
        for table, values in inventory['items'].items():
            session.add_all(ManagementItem(operation_id=operation.id, table_name=table, row_id=v) for v in values)
        return _dto(operation)


def operation_delete_preview(actor, operation_id, token, *, client=None):
    with write_transaction() as session:
        operation = _authorized_operation(session, actor, operation_id)
        if operation.stage != 'fenced' or operation.error_code != 'agent_reconfirmation_required':
            raise ManagementError(409, 'reconfirmation_not_required')
        inventory = frozen_inventory(operation)
        inventory['operation_id'] = operation.id
        inventory.pop('agent_counts', None)
        inventory['counts'] = {k: v for k, v in inventory['counts'].items() if not k.startswith('agent_')}
        inventory.update(agent_state='pending', agent_inventory_hash=None)
        preview = ManagementPreview(id=str(uuid4()), actor_id=actor.clinician_id, scope_json=operation.scope_json,
            inventory_json=_json(inventory), scope_hash=operation.scope_hash, expires_at=datetime.utcnow() + timedelta(minutes=10))
        session.add(preview)
        public = _preview_dto(preview)
    try:
        remote = (client or AgentDataManagementClient()).request('preview-inventory', _preview_payload(public), token)
        inventory.update(agent_counts=remote['counts'], agent_inventory_hash=remote['inventory_hash'],
                         agent_state='busy' if remote['busy'] else 'ready')
    except AgentManagementError:
        inventory.update(agent_state='unavailable')
    with write_transaction() as session:
        row = session.get(ManagementPreview, public['preview_id'])
        if row is None:
            raise ManagementError(409, 'preview_expired')
        row.inventory_json = _json(inventory)
        return _preview_dto(row)


def confirm_agent_inventory(actor, operation_id, request, token, *, client=None):
    validate('AgentInventoryConfirmationV1', request)
    public = get_delete_preview(actor, request['preview_id'])
    if (public['operation_id'] != operation_id or public['agent_state'] != 'ready'
            or public['agent_inventory_hash'] != request['expected_agent_inventory_hash']):
        raise ManagementError(409, 'agent_preview_stale')
    try:
        remote = (client or AgentDataManagementClient()).request('preview-inventory', _preview_payload(public), token)
    except AgentManagementError:
        raise ManagementError(503, 'agent_unavailable') from None
    if remote['busy'] or remote['inventory_hash'] != request['expected_agent_inventory_hash']:
        raise ManagementError(409, 'agent_preview_stale')
    with write_transaction() as session:
        row = _authorized_operation(session, actor, operation_id)
        preview = session.get(ManagementPreview, request['preview_id'])
        if preview is None or preview.expires_at <= datetime.utcnow() or preview.scope_hash != row.scope_hash:
            raise ManagementError(409, 'preview_expired')
        if row.stage != 'fenced' or row.error_code != 'agent_reconfirmation_required':
            raise ManagementError(409, 'reconfirmation_not_required')
        inventory = frozen_inventory(row)
        inventory['agent_inventory_hash'] = request['expected_agent_inventory_hash']
        inventory['counts'] = {k: v for k, v in inventory['counts'].items() if not k.startswith('agent_')}
        inventory['counts'].update({'agent_' + k: v for k, v in remote['counts'].items()})
        row.inventory_json, row.counts_json = _json(inventory), _json(inventory['counts'])
        row.state, row.error_code = 'running', None
        return _dto(row)


def get_operation(actor, operation_id):
    with write_transaction() as session:
        return _dto(_authorized_operation(session, actor, operation_id))


DELETE_MODELS = (ClinicalAuditEvent, IntegrationOutbox, SnapshotPublicationClaim, AgentSnapshotProjection,
    AnalysisSnapshot, SnapshotBuildAttempt, GaitSessionRevision, CollectionRadarTarget, CollectionRadarRaw,
    CollectionGpsRaw, CollectionInsoleFrame, DeviceTransformedData, DeviceRawData, CollectionSession)


def _purge_backend(session, operation):
    inventory = frozen_inventory(operation)
    for event in session.query(ClinicalAuditEvent).filter(ClinicalAuditEvent.id.in_(inventory['items']['clinical_audit_event'])):
        session.add(ManagementAuditBridge(event_hash=event.event_hash, previous_event_hash=event.previous_event_hash,
                                         operation_id=operation.id))
    session.flush()
    for model in DELETE_MODELS:
        values = inventory['items'].get(model.__tablename__, [])
        key = model.snapshot_id if model is AgentSnapshotProjection else model.capture_id if model is CollectionSession else model.id
        # Reverse self-FKs are deleted in topological order; frozen payloads are never rewritten.
        if model in (AnalysisSnapshot, GaitSessionRevision):
            parent = model.superseded_by_snapshot_id if model is AnalysisSnapshot else model.superseded_by_revision_id
            remaining = set(values)
            while remaining:
                referenced = {row[0] for row in session.query(parent).filter(parent.in_(remaining))}
                leaves = remaining - referenced
                if not leaves:
                    raise ManagementError(409, 'dependency_cycle')
                session.query(model).filter(key.in_(leaves)).delete(synchronize_session=False)
                remaining -= leaves
        else:
            session.query(model).filter(key.in_(values)).delete(synchronize_session=False)
        if session.query(model).filter(key.in_(values)).first() is not None:
            raise ManagementError(409, 'purge_verification_failed')


def continue_delete(actor, operation_id, token, *, client=None):
    operation = get_operation(actor, operation_id)
    if operation['agent_confirmation_required']:
        return operation
    if operation['stage'] == 'completed':
        return operation
    if operation['stage'] == 'fenced':
        payload = {key: operation[key] for key in ('operation_id', 'scope_hash', 'scope', 'snapshot_ids', 'session_ids', 'expected_agent_inventory_hash')}
        payload['schema_version'] = 1
        try:
            remote = (client or AgentDataManagementClient()).request('inventory', payload, token)
            if remote['busy']:
                raise AgentManagementError('agent_busy')
            if remote['confirmation_required']:
                raise AgentManagementError('agent_reconfirmation_required')
            receipt = (client or AgentDataManagementClient()).request('purge', payload, token)
            if not receipt['completed']:
                raise AgentManagementError('agent_purge_pending')
        except AgentManagementError as error:
            with write_transaction() as session:
                row = _authorized_operation(session, actor, operation_id)
                if row.stage == 'fenced':
                    row.state, row.error_code = 'retryable_failed', error.code
                return _dto(row)
        with write_transaction() as session:
            row = _authorized_operation(session, actor, operation_id)
            if row.stage == 'fenced':
                counts = json.loads(row.counts_json)
                counts.update({'agent_' + k: v for k, v in receipt['counts'].items()})
                row.counts_json = _json(counts)
                row.stage, row.state, row.error_code = 'agent_purged', 'running', None
    try:
        with write_transaction() as session:
            row = _authorized_operation(session, actor, operation_id)
            if row.stage == 'agent_purged':
                row.state, row.error_code = 'running', None
                session.flush()
                _purge_backend(session, row)
                row.stage, row.state, row.error_code = 'backend_purged', 'running', None
        with write_transaction() as session:
            row = _authorized_operation(session, actor, operation_id)
            if row.stage == 'backend_purged':
                row.stage, row.state, row.completed_at = 'completed', 'completed', datetime.utcnow()
                # Minimize receipts; frozen row lists are needed only until all phases succeed.
                inventory = frozen_inventory(row)
                row.inventory_json = _json({key: inventory[key] for key in ('snapshot_ids', 'session_ids', 'agent_inventory_hash')})
                session.query(ManagementItem).filter_by(operation_id=row.id).delete()
                session.query(ManagementPreview).filter_by(scope_json=row.scope_json).delete(synchronize_session=False)
            return _dto(row)
    except Exception:
        with write_transaction() as session:
            row = _authorized_operation(session, actor, operation_id)
            if row.stage != 'completed':
                row.state, row.error_code = 'retryable_failed', 'backend_purge_failed'
            return _dto(row)
