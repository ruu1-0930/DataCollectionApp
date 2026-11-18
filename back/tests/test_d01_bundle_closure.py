from datetime import datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from access import AccessError
from models.models import CollectionSession, DeviceRawData, Patient
from services import data_management as dm
from services.data_export import ExportInventory, ExportGrant
from tests.test_collection_ingest import batch, capture, event
from tests.test_collection_verification import create_v2, stop_v2


@pytest.fixture(autouse=True)
def management_routes(app):
    from api.data_management import data_management_bp
    app.register_blueprint(data_management_bp)


class Agent:
    def request(self, action, payload, token):
        if action == 'preview-inventory':
            return dict(counts={}, inventory_hash='a'*64, busy=False)
        if action == 'inventory':
            return dict(busy=False, confirmation_required=False)
        return dict(completed=True, counts={})


@pytest.fixture
def stopped(client, capture, db):
    assert create_v2(client, capture).status_code == 200
    assert batch(client, capture, [event()]).status_code == 200
    assert stop_v2(client, capture, {'insole':1, 'gps':0, 'radar':0}).status_code == 200
    cap = db.session.get(CollectionSession, capture['capture_id'])
    class SafeFixture(tuple):
        def __repr__(self):
            return 'SyntheticStoppedCapture()'
    return SafeFixture((capture, SimpleNamespace(clinician_id=cap.clinician_id), dict(kind='capture', patient_id=cap.patient_id, record_id=cap.capture_id)))


def add_export(db, patient, records=(), snapshots=(), sessions=(), *, whole=False, actor=999):
    now = datetime.utcnow()
    key = str(uuid4())
    row = ExportInventory(id=key, actor_id=actor, patient_id=patient,
        request_json=json.dumps(dict(scope='patient' if whole else 'records', record_ids=list(records))),
        inventory_json=json.dumps(dict(records=dict.fromkeys(records, {}), snapshots=[dict(id=s) for s in snapshots], session_ids=list(sessions))),
        scope_hash=key.replace('-', '')*2, state='ready', created_at=now, lease_until=now-timedelta(seconds=1), expires_at=now+timedelta(hours=1))
    db.session.add(row)
    db.session.flush()
    db.session.add(ExportGrant(token_hash=key.replace('-', '')*2, export_id=key, expires_at=now+timedelta(minutes=1)))
    db.session.commit()
    return dict(bundle_id=key, patient_id=patient, scope_hash=row.scope_hash)


def begin(stopped):
    _, actor, scope = stopped
    preview = dm.preview_delete(actor, scope, 'synthetic', client=Agent())
    return dm.begin_delete(actor, dict(request_id=str(uuid4()), preview_id=preview['preview_id'], discard_pending=False), 'synthetic', client=Agent())


def test_g1_backend_waits_for_workbench_purge_before_completed(stopped, db, monkeypatch):
    operation = begin(stopped)
    calls = []
    class Workbench:
        def purge(self, dto, token):
            calls.append(dto)
            raise RuntimeError('synthetic timeout')
    monkeypatch.setattr(dm, 'WorkbenchBundleClient', Workbench, raising=False)
    result = dm.continue_delete(stopped[1], operation['operation_id'], 'synthetic', client=Agent())
    assert result['stage'] == 'agent_purged'
    assert result['state'] == 'retryable_failed'
    assert len(calls) == 1
    assert DeviceRawData.query.count() == 2


def test_g2_preview_freezes_all_owners_intersecting_exports_and_rejects_changes(stopped, db):
    cap, actor, scope = stopped
    selected = add_export(db, scope['patient_id'], [cap['capture_id']])
    whole = add_export(db, scope['patient_id'], whole=True)
    keep = add_export(db, scope['patient_id'], [str(uuid4())])
    preview = dm.preview_delete(actor, scope, 'synthetic', client=Agent())
    assert preview['counts'].get('export_files') == 2
    late = add_export(db, scope['patient_id'], [cap['capture_id']])
    with pytest.raises(AccessError) as error:
        dm.begin_delete(actor, dict(request_id=str(uuid4()), preview_id=preview['preview_id'], discard_pending=False), 'synthetic', client=Agent())
    assert error.value.code == 'preview_stale'
    operation = begin(stopped)
    assert operation['export_files'] == sorted([selected, whole, late], key=lambda r:r['bundle_id'])
    assert keep not in operation['export_files']
    assert ExportGrant.query.filter(ExportGrant.export_id.in_([selected['bundle_id'], whole['bundle_id'], late['bundle_id']])).count() == 0


@pytest.mark.parametrize('failure', ['unavailable','operation','hash','count','pending','bool_count'])
def test_wb_failure_is_same_operation_retryable_then_cleans_inventory(stopped, db, monkeypatch, failure):
    cap, actor, scope = stopped
    selected = add_export(db, scope['patient_id'], [cap['capture_id']])
    keep = add_export(db, scope['patient_id'], [str(uuid4())])
    operation = begin(stopped)
    calls = []
    class Workbench:
        def purge(self, dto, token):
            calls.append(dto['operation_id'])
            # A callback observes a committed fence and full frozen binding.
            assert dm.get_operation(actor, dto['operation_id'])['export_files'] == [selected]
            result = dict(schema_version=1, operation_id=dto['operation_id'], scope_hash=dto['scope_hash'], completed=True, count=1)
            if len(calls) == 1:
                if failure == 'unavailable':
                    raise OSError('synthetic network failure')
                if failure == 'operation': result['operation_id'] = str(uuid4())
                if failure == 'hash': result['scope_hash'] = 'f'*64
                if failure == 'count': result['count'] = 0
                if failure == 'bool_count': result['count'] = True
                if failure == 'pending': result['completed'] = False
            return result
    monkeypatch.setattr(dm, 'WorkbenchBundleClient', Workbench)
    first = dm.continue_delete(actor, operation['operation_id'], 'synthetic', client=Agent())
    assert first['stage'] == 'agent_purged' and first['state'] == 'retryable_failed'
    assert DeviceRawData.query.count() == 2
    assert db.session.get(ExportInventory, selected['bundle_id']) is not None
    final = dm.continue_delete(actor, operation['operation_id'], 'synthetic', client=Agent())
    assert final['stage'] == 'completed' and final['export_files'] == [selected]
    assert calls == [operation['operation_id']]*2
    assert DeviceRawData.query.count() == 0 and Patient.query.count() == 1
    db.session.expire_all()
    assert db.session.get(ExportInventory, selected['bundle_id']) is None
    assert db.session.get(ExportInventory, keep['bundle_id']) is not None
    assert ExportGrant.query.filter_by(export_id=keep['bundle_id']).count() == 1
    assert dm.continue_delete(actor, operation['operation_id'], 'synthetic', client=Agent()) == final
    assert batch(__import__('flask').current_app.test_client(), cap, [event(seq=1)]).status_code == 410


def test_zero_export_files_still_requires_explicit_matching_wb_receipt(stopped, monkeypatch):
    operation = begin(stopped)
    assert operation['export_files'] == []
    calls = []
    class Workbench:
        def purge(self, dto, token):
            calls.append(dto['export_files'])
            return dict(schema_version=1, operation_id=dto['operation_id'], scope_hash=dto['scope_hash'], completed=True, count=0)
    monkeypatch.setattr(dm, 'WorkbenchBundleClient', Workbench)
    assert dm.continue_delete(stopped[1], operation['operation_id'], 'synthetic', client=Agent())['stage'] == 'completed'
    assert calls == [[]]


def test_workbench_client_is_bounded_and_posts_only_operation_id(app, monkeypatch):
    from services import workbench_bundle_client as module
    app.config['WORKBENCH_DATA_MANAGEMENT_URL'] = 'http://synthetic-wb.test'
    class Response:
        code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            assert size == 16385
            return b'{"schema_version":1}'
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'http://synthetic-wb.test/api/data-bundles/purge'
            assert timeout == 30
            assert json.loads(request.data) == dict(schema_version=1, operation_id='synthetic-operation')
            return Response()
    monkeypatch.setattr(module, 'build_opener', lambda handler: Opener())
    assert module.WorkbenchBundleClient().purge(dict(operation_id='synthetic-operation', scope={'patient_id':1}), 'synthetic') == {'schema_version':1}


def test_mixed_snapshot_and_session_export_intersections_are_frozen(stopped, db, client):
    cap, actor, scope = stopped
    result = client.post(f"/v3/patients/{cap['patient_id']}/collections/{cap['capture_id']}/snapshots:ensure", headers=cap['headers'])
    assert result.status_code == 201
    snapshot = result.get_json()['snapshot_id']
    by_snapshot = add_export(db, scope['patient_id'], [str(uuid4())], snapshots=[snapshot])
    by_session = add_export(db, scope['patient_id'], [str(uuid4())], sessions=['C:'+cap['capture_id']])
    keep = add_export(db, scope['patient_id'], [str(uuid4())], snapshots=[str(uuid4())])
    assert begin(stopped)['export_files'] == sorted([by_snapshot, by_session], key=lambda ref:ref['bundle_id'])


def test_backend_transaction_failure_retries_wb_and_keeps_frozen_exports(stopped, db, monkeypatch):
    _, actor, scope = stopped
    selected=add_export(db, scope['patient_id'], [scope['record_id']])
    operation=begin(stopped)
    calls=[]
    class Workbench:
        def purge(self,dto,token):
            calls.append(dto['operation_id'])
            return dict(schema_version=1,operation_id=dto['operation_id'],scope_hash=dto['scope_hash'],completed=True,count=1)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    original=dm._purge_backend
    failures=[]
    def fail_once(session,operation):
        original(session,operation)
        if not failures:
            failures.append(True)
            raise OSError('synthetic interrupted B transaction')
    monkeypatch.setattr(dm,'_purge_backend',fail_once)
    first=dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())
    assert first['stage']=='agent_purged' and first['error_code']=='backend_purge_failed'
    db.session.expire_all()
    assert DeviceRawData.query.count()==2 and db.session.get(ExportInventory,selected['bundle_id']) is not None
    final=dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())
    assert final['stage']=='completed' and calls==[operation['operation_id']]*2


def test_actual_snapshot_deletion_preserves_interleaved_audit_and_allows_append(stopped, db, client, monkeypatch):
    from datetime import timezone
    from models.models import ClinicalAuditEvent, AnalysisSnapshot
    from services.clinical_audit import write_audit, verify_patient_audit
    from services.collection_ingest import write_transaction
    cap,actor,scope=stopped
    def append():
        with write_transaction() as session:
            return write_audit(session,actor_id=actor.clinician_id,patient_id=scope['patient_id'],trace_id=str(uuid4()),
                action='snapshot.read',result='ok',now=datetime.now(timezone.utc)).id
    first=append()
    result=client.post(f"/v3/patients/{cap['patient_id']}/collections/{cap['capture_id']}/snapshots:ensure",headers=cap['headers'])
    assert result.status_code==201
    last=append()
    before={row.id:(row.canonical_payload,row.event_hash) for row in ClinicalAuditEvent.query.filter(ClinicalAuditEvent.id.in_([first,last]))}
    operation=begin(stopped)
    class Workbench:
        def purge(self,dto,token):return dict(schema_version=1,operation_id=dto['operation_id'],scope_hash=dto['scope_hash'],completed=True,count=0)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    final=dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())
    assert final['stage']=='completed' and AnalysisSnapshot.query.count()==0
    db.session.expire_all()
    assert {row.id:(row.canonical_payload,row.event_hash) for row in ClinicalAuditEvent.query.all()}==before
    verify_patient_audit(db.session,scope['patient_id'])
    append()
    verify_patient_audit(db.session,scope['patient_id'])


def test_legacy_deletion_preserves_other_patient_pii_device_and_audit(admin_data, admin_scope, db, monkeypatch):
    from models.models import PatientPII, Device, Clinician, AnalysisSnapshot
    from services.clinical_audit import verify_patient_audit
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    scope=dict(kind='legacy_session',patient_id=admin_data['patient_id'],record_id=admin_data['session_id'])
    before={model.__tablename__:[tuple(getattr(row,c.name) for c in model.__table__.columns) for row in db.session.query(model).order_by(list(model.__table__.primary_key)[0])] for model in (Patient,PatientPII,Device,Clinician)}
    kept_raw=db.session.query(DeviceRawData).filter_by(patient_id=admin_data['other_patient_id']).one()
    raw_bytes=tuple(getattr(kept_raw,c.name) for c in DeviceRawData.__table__.columns)
    preview=dm.preview_delete(actor,scope,'synthetic',client=Agent())
    operation=dm.begin_delete(actor,dict(request_id=str(uuid4()),preview_id=preview['preview_id'],discard_pending=False),'synthetic',client=Agent())
    class Workbench:
        def purge(self,dto,token):return dict(schema_version=1,operation_id=dto['operation_id'],scope_hash=dto['scope_hash'],completed=True,count=0)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    assert dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())['stage']=='completed'
    db.session.expire_all()
    assert AnalysisSnapshot.query.count()==0 and DeviceRawData.query.count()==1
    assert tuple(getattr(DeviceRawData.query.one(),c.name) for c in DeviceRawData.__table__.columns)==raw_bytes
    for model in (Patient,PatientPII,Device,Clinician):
        assert [tuple(getattr(row,c.name) for c in model.__table__.columns) for row in db.session.query(model).order_by(list(model.__table__.primary_key)[0])]==before[model.__tablename__]
    verify_patient_audit(db.session,scope['patient_id'])


def test_capture_preserves_other_capture_and_shared_device(stopped, client, db, monkeypatch):
    from tests.test_collection_records import other_capture
    from models.models import Device
    cap,actor,scope=stopped
    other=other_capture(cap,0)
    assert create_v2(client,other).status_code==200
    assert batch(client,other,[event()]).status_code==200
    assert stop_v2(client,other,{'insole':1,'gps':0,'radar':0}).status_code==200
    before=sorted((r.id,r.p1,r.collected_at) for r in DeviceRawData.query.all() if r.id>2)
    operation=begin(stopped)
    assert batch(client,cap,[event(seq=1)]).status_code==409
    class Workbench:
        def purge(self,dto,token):return dict(schema_version=1,operation_id=dto['operation_id'],scope_hash=dto['scope_hash'],completed=True,count=0)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    assert dm.continue_delete(actor,operation['operation_id'],'synthetic',client=Agent())['stage']=='completed'
    db.session.expire_all()
    assert CollectionSession.query.one().capture_id==other['capture_id']
    assert sorted((r.id,r.p1,r.collected_at) for r in DeviceRawData.query.all())==before
    assert Device.query.count()==1


def test_mixed_historical_snapshot_is_disclosed_and_its_package_selected(capture, db, client, monkeypatch):
    from tests.test_collection_records import _legacy_left
    from services.gait_session_revision import _session_id
    cap=capture
    monkeypatch.setattr('services.collection_ingest.server_now',lambda:datetime(2020,1,1))
    assert create_v2(client,cap).status_code==200
    assert batch(client,cap,[event()]).status_code==200
    assert stop_v2(client,cap,{'insole':1,'gps':0,'radar':0}).status_code==200
    registered=db.session.get(CollectionSession,cap['capture_id'])
    actor=SimpleNamespace(clinician_id=registered.clinician_id)
    scope=dict(kind='capture',patient_id=cap['patient_id'],record_id=cap['capture_id'])
    raw_at=DeviceRawData.query.first().collected_at
    _legacy_left(db,registered,raw_at)
    # Valid historical pre-capture snapshot, as in existing capture/snapshot regression fixtures.
    registered.metadata_schema_version=None
    db.session.commit()
    path=f"/patients/{cap['patient_id']}/gait/sessions/{_session_id(cap['patient_id'],raw_at)}/snapshots:ensure"
    result=client.post(path,headers=cap['headers'])
    assert result.status_code==201
    sid=result.get_json()['snapshot_id']
    registered.metadata_schema_version=1
    db.session.commit()
    ref=add_export(db,scope['patient_id'],[str(uuid4())],snapshots=[sid])
    preview=dm.preview_delete(actor,scope,'synthetic',client=Agent())
    assert preview['extra_affected_results']==[sid]
    assert begin((cap,actor,scope))['export_files']==[ref]


def test_actual_management_http_resume_and_callback_authorization(stopped, db, client, monkeypatch):
    cap,actor,scope=stopped
    selected=add_export(db,scope['patient_id'],[cap['capture_id']])
    monkeypatch.setattr(dm,'AgentDataManagementClient',Agent)
    base='/v2/data-management'
    headers=cap['headers']
    preview=client.post(base+'/delete-previews',json=scope,headers=headers)
    assert preview.status_code==200
    request=dict(request_id=str(uuid4()),preview_id=preview.get_json()['preview_id'],discard_pending=False)
    operation=client.post(base+'/operations',json=request,headers=headers)
    assert operation.status_code==200 and operation.get_json()['export_files']==[selected]
    key=operation.get_json()['operation_id']
    calls=[]
    class Workbench:
        def purge(self,dto,token):
            response=client.get(base+'/operations/'+key,headers=headers)
            assert response.status_code==200 and response.get_json()['stage']=='agent_purged'
            assert response.get_json()['export_files']==[selected]
            assert client.get(base+'/operations/'+key).status_code==401
            calls.append(key)
            if len(calls)==1:raise TimeoutError('synthetic lost response')
            return dict(schema_version=1,operation_id=key,scope_hash=dto['scope_hash'],completed=True,count=1)
    monkeypatch.setattr(dm,'WorkbenchBundleClient',Workbench)
    first=client.post(base+'/operations/'+key+'/continue',json={},headers=headers)
    assert first.status_code==200 and first.get_json()['stage']=='agent_purged'
    # Same request recovers the existing operation even after its preview is no longer needed.
    assert client.post(base+'/operations',json=request,headers=headers).get_json()['operation_id']==key
    final=client.post(base+'/operations/'+key+'/continue',json={},headers=headers)
    assert final.status_code==200 and final.get_json()['stage']=='completed'
    assert calls==[key,key]
