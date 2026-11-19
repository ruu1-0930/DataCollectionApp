from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from access import AccessError
from config import create_app
from models.models import Patient, PatientPII, Device, DeviceRawData, Clinician
from services import data_management as dm
from services.clinical_audit import verify_patient_audit, write_audit
from services.data_export import ExportGrant, ExportInventory
from services.data_management_scope import ManagementItem, ManagementPreview, assert_clinical_scope
from tests.test_collection_ingest import batch, capture, event, stamp
from tests.test_collection_verification import create_v2, stop_v2
from tests.test_d01_bundle_closure import Agent, stopped, management_routes, add_export
from tests.test_radar_ingest import radar_event
from tests.test_raw_data import _frame


def whole(actor, patient):
    return dm.preview_delete(actor, dict(kind='patient',patient_id=patient,record_id=None),'synthetic',client=Agent())


def begin(preview, actor, **extra):
    return dm.begin_delete(actor, dict(request_id=str(uuid4()),preview_id=preview['preview_id'],discard_pending=True, **extra),'synthetic',client=Agent())


def test_patient_delete_removes_personal_data_preserves_other_patient_shared_device_and_resumes(admin_data,admin_scope,db,monkeypatch):
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    pid=admin_data['patient_id']; other=admin_data['other_patient_id']
    # A shared device continues to serve the other patient.
    kept=DeviceRawData.query.filter_by(patient_id=other).one()
    kept.device_id=admin_data['device_id']; db.session.commit()
    before={m.__tablename__:[tuple(getattr(r,c.name) for c in m.__table__.columns) for r in m.query.all()] for m in (Device,Clinician)}
    kept_raw=tuple(getattr(kept,c.name) for c in DeviceRawData.__table__.columns)
    package=add_export(db,pid,whole=True)
    preview=whole(actor,pid)
    assert preview['scope']['record_id'] is None and preview['counts']['patients']==1
    operation=begin(preview,actor,confirm_patient_id=pid)
    calls=[]
    class Workbench:
        def purge(self,dto,token):
            calls.append(dto['operation_id'])
            assert dto['export_files']==[package]
            if len(calls)==1: raise OSError('injected lost receipt')
            return dict(schema_version=1,operation_id=dto['operation_id'],scope_hash=dto['scope_hash'],completed=True,count=1)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    first=dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())
    assert first['stage']=='agent_purged' and db.session.get(Patient,pid) is not None
    final=dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())
    assert final['stage']=='completed'
    db.session.expire_all()
    assert db.session.get(Patient,pid) is None and db.session.get(PatientPII,pid) is None
    assert tuple(getattr(DeviceRawData.query.one(),c.name) for c in DeviceRawData.__table__.columns)==kept_raw
    for m in (Device,Clinician):
        assert [tuple(getattr(r,c.name) for c in m.__table__.columns) for r in m.query.all()]==before[m.__tablename__]
    assert dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())==final
    with pytest.raises(AccessError,match='scope_deleted'): assert_clinical_scope(db.session,pid)
    assert 'synthetic-patient-0' not in json.dumps(final)
    assert final['snapshot_ids'] == final['session_ids'] == final['export_files'] == []


def test_patient_confirmation_is_required_and_changed_profile_invalidates_preview(stopped,db):
    _,actor,scope=stopped
    preview=whole(actor,scope['patient_id'])
    for supplied in ({},{'confirm_patient_id':scope['patient_id']+1}):
        with pytest.raises(AccessError,match='patient_confirmation_required'):begin(preview,actor,**supplied)
    patient=db.session.get(Patient,scope['patient_id']); patient.age=61;db.session.commit()
    with pytest.raises(AccessError,match='preview_stale'):begin(preview,actor,confirm_patient_id=patient.id)


def test_whole_patient_fence_blocks_legacy_upload_and_directories_until_capture_ids_are_retired(
        stopped, client, db, monkeypatch):
    cap, actor, scope = stopped
    pid = scope['patient_id']
    headers = cap['headers']
    preview = whole(actor, pid)
    request = {'request_id': str(uuid4()), 'preview_id': preview['preview_id'],
               'discard_pending': False, 'confirm_patient_id': pid}
    operation = dm.begin_delete(actor, request, 'synthetic', client=Agent())
    assert dm.begin_delete(actor, request, 'synthetic', client=Agent()) == operation
    with pytest.raises(AccessError, match='patient_confirmation_required'):
        dm.begin_delete(actor, dict(request, confirm_patient_id=pid+1), 'synthetic', client=Agent())
    assert client.get(f'/v2/patients/{pid}/profile', headers=headers).status_code == 409
    profile = dict(name='Synthetic duplicate', gender='男', age=60, height_cm=170,
                   weight_kg=63, shoe_size_eu=41, phone='13900000000')
    assert client.put(f'/v2/patients/{pid}/profile', json=profile, headers=headers).status_code == 409
    for url in ('/patients', '/workbench/patients'):
        data = client.get(url, headers=headers).get_json()['data']
        assert (data if isinstance(data, list) else data['items']) == []
    body = dict(_frame(), patient_id=pid)
    assert client.post('/devices/INSOLE-001/raw_data', json=body, headers=headers).status_code == 409
    assert batch(client, cap, [event(seq=1)]).status_code == 409

    class Workbench:
        def purge(self, dto, token):
            return dict(schema_version=1, operation_id=dto['operation_id'], scope_hash=dto['scope_hash'],
                        completed=True, count=0)

    monkeypatch.setattr(dm, 'WorkbenchBundleClient', Workbench)
    assert dm.continue_delete(actor, operation['operation_id'], 'synthetic', client=Agent())['stage'] == 'completed'
    assert client.post('/devices/INSOLE-001/raw_data', json=body, headers=headers).status_code == 410
    assert batch(client, cap, [event(seq=1)]).status_code == 410
    assert stop_v2(client, cap, {'insole': 1, 'gps': 0, 'radar': 0}).status_code == 410
    assert create_v2(client, cap).status_code == 410
    new_cap = dict(cap, body=dict(cap['body'], capture_id=str(uuid4())))
    assert create_v2(client, new_cap).status_code == 410
    replacement = client.post('/v2/patients', headers=headers, json=profile)
    assert replacement.status_code == 200
    replacement_id = replacement.get_json()['data']['id']
    assert replacement_id != pid
    with pytest.raises(IntegrityError, match='patient identity retired'):
        db.session.execute(text('INSERT INTO patients (id, clinician_id, subject_id) VALUES (:pid, :owner, :subject)'),
                           dict(pid=pid, owner=actor.clinician_id, subject='#retired'))
    db.session.rollback()
    reuse = dict(cap, patient_id=replacement_id, body=dict(cap['body'], patient_id=replacement_id))
    assert create_v2(client, reuse).status_code == 410
    assert dm.begin_delete(actor, request, 'synthetic', client=Agent())['stage'] == 'completed'


def test_patient_reconfirmation_after_agent_changes_requires_typed_id_and_uses_original_operation(stopped):
    _, actor, scope = stopped
    pid = scope['patient_id']
    original = begin(whole(actor, pid), actor, confirm_patient_id=pid)

    class ChangedAgent(Agent):
        def request(self, action, payload, token):
            if action == 'inventory':
                return dict(busy=False, confirmation_required=True)
            return dict(counts={'report': 2}, inventory_hash='b' * 64, busy=False)

    agent = ChangedAgent()
    operation_id = original['operation_id']
    stale = dm.continue_delete(actor, operation_id, 'synthetic', client=agent)
    assert stale['agent_confirmation_required']
    preview = dm.operation_delete_preview(actor, operation_id, 'synthetic', client=agent)
    request = dict(preview_id=preview['preview_id'], expected_agent_inventory_hash='b' * 64)
    with pytest.raises(AccessError, match='patient_confirmation_required'):
        dm.confirm_agent_inventory(actor, operation_id, request, 'synthetic', client=agent)
    confirmed = dm.confirm_agent_inventory(actor, operation_id, dict(request, confirm_patient_id=pid),
                                           'synthetic', client=agent)
    assert confirmed['operation_id'] == operation_id
    assert confirmed['counts']['agent_report'] == 2
    assert confirmed['agent_confirmation_required'] is False


def test_patient_delete_covers_legacy_and_all_capture_streams_without_crossing_shared_device(
        admin_data, admin_scope, db, client, monkeypatch):
    from models.models import (AnalysisSnapshot, ClinicalAuditEvent, CollectionGpsRaw,
        CollectionInsoleFrame, CollectionRadarRaw, CollectionRadarTarget, CollectionSession,
        DeviceTransformedData, IntegrationOutbox, SnapshotBuildAttempt, GaitSessionRevision,
        AgentSnapshotProjection)

    pid = admin_data['patient_id']
    other = admin_data['other_patient_id']
    doctor = admin_scope['doctor_a']
    owner = SimpleNamespace(clinician_id=doctor['id'])
    target_device = db.session.get(Device, admin_data['device_id'])
    patient_neighbor = db.session.get(Patient, other)
    # Two patients of one doctor use one device; the neighbor also has its own audit chain.
    patient_neighbor.clinician_id = owner.clinician_id
    neighbor_raw = DeviceRawData.query.filter_by(patient_id=other).one()
    neighbor_raw.clinician_id, neighbor_raw.device_id = owner.clinician_id, target_device.id
    neighbor_audit = write_audit(db.session, actor_id=owner.clinician_id, patient_id=other,
        trace_id=str(uuid4()), action='snapshot.read', result='ok', now=datetime.now(timezone.utc))
    neighbor_audit_hash = neighbor_audit.event_hash
    original = db.session.get(DeviceRawData, admin_data['raw_ids'][0])
    orphan_values = {c.name: getattr(original, c.name) for c in DeviceRawData.__table__.columns if c.name != 'id'}
    orphan = DeviceRawData(**orphan_values)
    db.session.add(orphan)
    db.session.flush()
    orphan.collected_at = None
    db.session.commit()
    assert db.session.execute(text('PRAGMA foreign_keys')).scalar_one() == 1

    def populate(current_patient, offset):
        record_id = str(uuid4())
        cap = dict(capture_id=record_id, patient_id=current_patient, headers=doctor['headers'],
                   body=dict(capture_id=record_id, patient_id=current_patient, device_code=target_device.device_code,
                             mobile_started_at=stamp(offset)))
        assert create_v2(client, cap).status_code == 200
        for sample in (event(ms=offset + 500), event(ms=offset + 500, stream='gps'), radar_event(ms=offset + 500)):
            assert batch(client, cap, [sample]).status_code == 200
        assert stop_v2(client, cap, {'insole': 1, 'gps': 1, 'radar': 1}).status_code == 200
        snapshot = client.post(f'/v3/patients/{current_patient}/collections/{record_id}/snapshots:ensure',
                               headers=doctor['headers'])
        assert snapshot.status_code == 201
        return record_id, snapshot.get_json()['snapshot_id']

    target = populate(pid, 0)
    neighbor = populate(other, 1)
    target_package = add_export(db, pid, [target[0]], actor=admin_scope['admin']['id'])
    neighbor_package = add_export(db, other, [neighbor[0]], actor=owner.clinician_id)
    outsider = SimpleNamespace(clinician_id=admin_scope['doctor_b']['id'])
    with pytest.raises(AccessError, match='forbidden'):
        whole(outsider, pid)
    other_preview = whole(owner, other)
    target_preview = whole(owner, pid)
    assert target_preview['counts']['device_raw_data'] == 7
    assert target_preview['counts']['device_transformed_data'] == 1
    assert target_preview['counts']['collection_radar_targets'] == 1
    assert set(target_preview['snapshot_ids']) == {target[1], admin_data['snapshot_id']}
    operation = begin(target_preview, owner, confirm_patient_id=pid)
    with pytest.raises(AccessError, match='forbidden'):
        dm.get_operation(outsider, operation['operation_id'])
    assert ExportGrant.query.filter_by(export_id=target_package['bundle_id']).count() == 0

    class Workbench:
        def purge(self, dto, token):
            assert dto['export_files'] == [target_package]
            return dict(schema_version=1, operation_id=dto['operation_id'], scope_hash=dto['scope_hash'],
                        completed=True, count=1)

    monkeypatch.setattr(dm, 'WorkbenchBundleClient', Workbench)
    assert dm.continue_delete(owner, operation['operation_id'], 'synthetic', client=Agent())['stage'] == 'completed'
    db.session.expire_all()
    assert Patient.query.one().id == PatientPII.query.one().patient_id == other
    for model in (CollectionSession, CollectionInsoleFrame, CollectionGpsRaw, CollectionRadarRaw):
        assert model.query.one().capture_id == neighbor[0]
    assert CollectionRadarTarget.query.one().parent_id == CollectionRadarRaw.query.one().id
    assert {raw.patient_id for raw in DeviceRawData.query.all()} == {other}
    assert DeviceTransformedData.query.count() == 0
    assert AnalysisSnapshot.query.one().id == AgentSnapshotProjection.query.one().snapshot_id == neighbor[1]
    assert SnapshotBuildAttempt.query.one().identity_fingerprint == AnalysisSnapshot.query.one().identity_fingerprint
    assert GaitSessionRevision.query.one().patient_id == other
    assert all(outbox.patient_id == other for outbox in IntegrationOutbox.query.all())
    assert {event.patient_id for event in ClinicalAuditEvent.query.all()} == {other}
    assert neighbor_audit_hash in {event.event_hash for event in ClinicalAuditEvent.query.all()}
    verify_patient_audit(db.session, other)
    assert ExportInventory.query.one().id == ExportGrant.query.one().export_id == neighbor_package['bundle_id']
    assert ManagementPreview.query.one().id == other_preview['preview_id']
    tombstone = ManagementItem.query.one()
    assert (tombstone.table_name, tombstone.row_id) == ('collection_sessions', target[0])
    assert Device.query.count() == 2 and Clinician.query.count() == 3


def test_active_collection_export_snapshot_and_agent_work_block_patient_delete(client, capture, db):
    from models.models import SnapshotBuildAttempt

    pid = capture['patient_id']
    actor = SimpleNamespace(clinician_id=db.session.get(Patient, pid).clinician_id)
    assert create_v2(client, capture).status_code == 200
    with pytest.raises(AccessError, match='collection_in_progress'):
        whole(actor, pid)
    assert stop_v2(client, capture, {'insole': 1, 'gps': 0, 'radar': 0}).status_code == 200
    pending = whole(actor, pid)
    with pytest.raises(AccessError, match='pending_upload_confirmation_required'):
        dm.begin_delete(actor, dict(preview_id=pending['preview_id'], request_id=str(uuid4()),
            discard_pending=False, confirm_patient_id=pid), 'synthetic', client=Agent())

    package = add_export(db, pid, whole=True)
    export = db.session.get(ExportInventory, package['bundle_id'])
    export.state = 'building'
    export.lease_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5)
    db.session.commit()
    with pytest.raises(AccessError, match='export_in_progress'):
        whole(actor, pid)
    export.state = 'ready'
    trace = str(uuid4())
    write_audit(db.session, actor_id=actor.clinician_id, patient_id=pid, trace_id=trace,
                action='snapshot.build', result='running', now=datetime.now(timezone.utc))
    attempt = SnapshotBuildAttempt(id=str(uuid4()), identity_fingerprint='x' * 64,
        attempt_number=1, trace_id=trace, state='running')
    db.session.add(attempt)
    db.session.commit()
    with pytest.raises(AccessError, match='snapshot_building'):
        whole(actor, pid)
    attempt.state = 'failed'
    db.session.commit()

    class BusyAgent(Agent):
        def request(self, action, payload, token):
            return dict(counts={'memory_intent': 1}, inventory_hash='b' * 64, busy=True)

    busy = dm.preview_delete(actor, dict(kind='patient', patient_id=pid, record_id=None),
                            'synthetic', client=BusyAgent())
    assert busy['agent_state'] == 'busy'
    with pytest.raises(AccessError, match='agent_preview_not_ready'):
        begin(busy, actor, confirm_patient_id=pid)


def test_cross_patient_audit_dependency_refuses_preview_without_remote_call(admin_data, admin_scope, db):
    other = admin_data['other_patient_id']
    write_audit(db.session, actor_id=admin_scope['doctor_b']['id'], patient_id=other,
        trace_id=str(uuid4()), action='snapshot.read', result='ok', now=datetime.now(timezone.utc),
        snapshot_id=admin_data['snapshot_id'])
    db.session.commit()

    class AgentMustNotRun:
        def request(self, *_):
            pytest.fail('B must reject dependencies before making a remote call')

    actor = SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    with pytest.raises(AccessError, match='cross_patient_dependency'):
        dm.preview_delete(actor, dict(kind='patient', patient_id=admin_data['patient_id'], record_id=None),
                          'synthetic', client=AgentMustNotRun())


def test_patient_delete_triggers_reject_plain_sql_and_bootstrap_matches_011(db, stopped):
    _, _, scope = stopped
    for table, column in (('patients', 'id'), ('patient_pii', 'patient_id')):
        with pytest.raises(IntegrityError, match='scoped management required'):
            db.session.execute(text(f'DELETE FROM {table} WHERE {column} = :pid'), {'pid': scope['patient_id']})
        db.session.rollback()
    root = Path(__file__).resolve().parents[1]
    migration = (root / 'migrations/011_whole_patient_data_management.sql').read_text(encoding='utf-8')
    bootstrap = (root / 'database_schema_mysql.sql').read_text(encoding='utf-8')
    for definition in migration.split('DELIMITER $$\n')[1].split('DELIMITER ;')[0].strip().split('END$$'):
        if definition.strip():
            assert definition.strip() + '\nEND$$' in bootstrap
    assert 'DROP TRIGGER' not in migration


def test_management_stays_disabled_before_011(tmp_path, monkeypatch, db):
    uri = 'sqlite:///' + (tmp_path / 'migration-010.sqlite').as_posix()
    monkeypatch.delenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', raising=False)
    config = {'SQLALCHEMY_DATABASE_URI': uri, 'TESTING': True}
    seed = create_app(config)
    with seed.app_context():
        db.create_all()
        db.session.execute(text('DROP INDEX ix_management_item_identity'))
        db.session.commit()
    assert seed.test_client().post('/v2/data-management/delete-previews').status_code == 404
    monkeypatch.setenv('SARCOGAIT_DATA_MANAGEMENT_ENABLED', 'true')
    monkeypatch.setenv('SARCOGAIT_WORKBENCH_URL', 'http://127.0.0.1:8000')
    with pytest.raises(RuntimeError, match='data_management_requires_migration_011'):
        create_app(config)
