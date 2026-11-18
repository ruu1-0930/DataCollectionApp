from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import json
import pytest
from access import AccessError
from models.models import DeviceTransformedData
from services import data_export as exports


def request(patient, records):
    return dict(schema_version=1, request_id=str(uuid4()), patient_id=patient, scope='records',
                record_ids=records, mode='backup', contents=['profiles','raw','analysis','agent'])


def test_g1_backup_freezes_and_pages_existing_transforms_only_selected_raw_ids(admin_data, admin_scope, db):
    data=admin_data
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    req=request(data['patient_id'],[data['session_id']])
    frozen=exports.create_export_inventory(actor,req)
    page=exports.read_export_page(actor,frozen['export_id'],'transformed',record_id=data['session_id'])
    original=DeviceTransformedData.query.one()
    assert page['items']==[exports._row(original)]
    assert frozen['inventory']['records'][data['session_id']]['transformed']['count']==1
    original.T1=-1.2345678901234567
    db.session.commit()
    with pytest.raises(AccessError,match='export_scope_changed'):
        exports.read_export_page(actor,frozen['export_id'],'frames',record_id=data['session_id'])

from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
import os

from jsonschema import Draft202012Validator
from models.models import DeviceRawData


def all_pages(actor, frozen, kind, record=None):
    rows=[]; cursor=None; pages=[]
    while True:
        page=exports.read_export_page(actor,frozen['export_id'],kind,cursor,record_id=record)
        Draft202012Validator(json.loads((Path(__file__).parents[1]/'contracts/data_export_v1.schema.json').read_text(encoding='utf8'))['contracts']['ExportPageV1']).validate(page)
        pages.append(deepcopy(page)); rows.extend(page['items'])
        cursor=page['next_cursor']
        if cursor is None:return rows,pages


def test_g1_1201_frames_precise_stored_transforms_and_page_fingerprint(admin_data, admin_scope, db):
    data=admin_data
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    first=db.session.get(DeviceRawData,data['raw_ids'][0])
    # 1201 logical frames, with a real absent right foot in the final frame.
    for n in range(2,1201):
        for side in (('L',) if n==1200 else ('L','R')):
            raw=DeviceRawData(**{c.key:getattr(first,c.key) for c in DeviceRawData.__table__.columns if c.key!='id'})
            raw.foot=side; raw.collected_at=first.collected_at+timedelta(milliseconds=n)
            raw.ax=-1.2345678901234567
            db.session.add(raw); db.session.flush()
            if side=='L':
                db.session.add(DeviceTransformedData(raw_data_id=raw.id,T1=-1.2345678901234567,T2=1e-12,T3=0,T4=4,T5=5,
                    created_at=datetime(2026,11,19,1,2,3,456789)))
    other=db.session.get(DeviceRawData,data['other_raw_id']) if 'other_raw_id' in data else DeviceRawData.query.filter_by(patient_id=data['other_patient_id']).one()
    db.session.add(DeviceTransformedData(raw_data_id=other.id,T1=999,T2=999,T3=999,T4=999,T5=999))
    db.session.commit()
    req=request(data['patient_id'],[data['session_id']])
    frozen=exports.create_export_inventory(actor,req)
    frames,frame_pages=all_pages(actor,frozen,'frames',data['session_id'])
    transformed,pages=all_pages(actor,frozen,'transformed',data['session_id'])
    assert len(frames)==1201 and frames[-1]['right'] is None
    assert len(frame_pages)>1 and len(pages)>1 and len(transformed)==1200
    selected={r[side]['id'] for r in frames for side in ('left','right') if r[side]}
    assert {r['raw_data_id'] for r in transformed}<=selected
    assert transformed[-1]['T1']==-1.2345678901234567
    assert transformed[-1]['created_at']=='2026-11-19T01:02:03.456789'
    fp=frozen['inventory']['records'][data['session_id']]['transformed']
    assert fp==dict(count=len(transformed),sha256=sha256(b''.join(exports.encoded(r)+b'\n' for r in transformed)).hexdigest())
    if os.getenv('D02_SYNTHETIC_FIXTURE'):
        fixture=dict(frozen=frozen,pages={})
        for kind in ('patients','snapshots'):
            fixture['pages'][kind]=all_pages(actor,frozen,kind)[1]
        for kind in ('collections','frames','transformed','gps','radar','targets'):
            fixture['pages'][kind]=all_pages(actor,frozen,kind,data['session_id'])[1]
        Path(os.environ['D02_SYNTHETIC_FIXTURE']).write_text(json.dumps(fixture,ensure_ascii=False),encoding='utf8')


@pytest.mark.parametrize('mutation',['append','unlink_scope','update'])
def test_g1_transformed_mutation_invalidates_entire_frozen_export(admin_data,admin_scope,db,mutation):
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    frozen=exports.create_export_inventory(actor,request(admin_data['patient_id'],[admin_data['session_id']]))
    row=DeviceTransformedData.query.one()
    if mutation=='append':db.session.add(DeviceTransformedData(raw_data_id=admin_data['raw_ids'][1],T1=1,T2=2,T3=3,T4=4,T5=5))
    if mutation=='unlink_scope':row.raw_data_id=DeviceRawData.query.filter_by(patient_id=admin_data['other_patient_id']).one().id
    if mutation=='update':row.T5=9
    db.session.commit()
    with pytest.raises(AccessError,match='export_scope_changed'):exports.finish_export(actor,frozen['export_id'],'ready')


def test_g1_raw_only_does_not_expand_to_analysis(admin_data,admin_scope):
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    req=request(admin_data['patient_id'],[admin_data['session_id']]); req.update(mode='export',contents=['raw'])
    frozen=exports.create_export_inventory(actor,req)
    assert frozen['inventory']['records'][admin_data['session_id']]['transformed'] is None
    with pytest.raises(AccessError,match='content_not_selected'):exports.read_export_page(actor,frozen['export_id'],'transformed',record_id=admin_data['session_id'])

from tests.test_collection_ingest import batch, capture, event
from tests.test_collection_verification import create_v2, stop_v2
from models.models import CollectionSession


def test_g1_capture_uses_its_exact_raw_links_and_rejects_other_record(client,capture,db):
    assert create_v2(client,capture).status_code==200
    assert batch(client,capture,[event()]).status_code==200
    assert stop_v2(client,capture,dict(insole=1,gps=0,radar=0)).status_code==200
    cap=db.session.get(CollectionSession,capture['capture_id'])
    raw=DeviceRawData.query.filter_by(patient_id=cap.patient_id).first()
    saved=DeviceTransformedData(raw_data_id=raw.id,T1=123.456,T2=-2,T3=3,T4=4,T5=5)
    db.session.add(saved); db.session.commit()
    actor=SimpleNamespace(clinician_id=cap.clinician_id)
    frozen=exports.create_export_inventory(actor,request(cap.patient_id,[cap.capture_id]))
    rows,_=all_pages(actor,frozen,'transformed',cap.capture_id)
    assert rows==[exports._row(saved)]
    with pytest.raises(AccessError,match='scope_mismatch'):
        exports.read_export_page(actor,frozen['export_id'],'transformed',record_id=str(uuid4()))


def test_g1_contract_copies_are_strict_about_transform_fingerprint(admin_data,admin_scope):
    actor=SimpleNamespace(clinician_id=admin_scope['doctor_a']['id'])
    frozen=exports.create_export_inventory(actor,request(admin_data['patient_id'],[admin_data['session_id']]))
    schema=json.loads((Path(__file__).parents[1]/'contracts/data_export_v1.schema.json').read_text(encoding='utf8'))['contracts']['ExportInventoryV1']
    check=Draft202012Validator(schema); check.validate(frozen)
    for change in ('missing','extra','hash','negative'):
        invalid=deepcopy(frozen); record=invalid['inventory']['records'][admin_data['session_id']]
        if change=='missing':record.pop('transformed')
        if change=='extra':record['transformed']['recomputed']=True
        if change=='hash':record['transformed']['sha256']='not-hash'
        if change=='negative':record['transformed']['count']=-1
        assert not check.is_valid(invalid)
