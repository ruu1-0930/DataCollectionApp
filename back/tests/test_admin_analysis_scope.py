"""An administrator acts as themself when analysing another doctor's patient."""

from datetime import datetime
from uuid import uuid4

import pytest
from models.models import ClinicalAuditEvent, DeviceRawData
from services.gait_session_revision import _session_id
from services.snapshot_repository import AnalysisSnapshotRepository


def test_admin_claim_keeps_actual_actor(client, admin_scope, admin_data):
    pid = admin_data['patient_id']
    h = admin_scope['admin']['headers']
    response = client.post(
        f"/patients/{pid}/gait/sessions/{admin_data['session_id']}/snapshots:ensure", headers=h, json={})
    assert response.status_code in (200, 201), response.get_json()
    snapshot = response.get_json()
    claim = client.post(f"/patients/{pid}/gait/snapshots/{snapshot['snapshot_id']}/publication-claims",
        headers=h, json={'snapshot_state_version': snapshot['snapshot_state_version'],
                        'workflow_run_id': str(uuid4()), 'candidate_hash': 'a' * 64})
    assert claim.status_code in (200, 201), claim.get_json()
    assert claim.get_json()['actor_id'] == admin_scope['admin']['id']
    assert ClinicalAuditEvent.query.filter_by(actor_id=admin_scope['admin']['id'], patient_id=pid).count() > 0
    assert client.get(f'/patients/{pid}', headers=admin_scope['doctor_b']['headers']).status_code == 403


def test_admin_builds_a_new_snapshot_without_changing_raw_owner(client, db, admin_scope, admin_data):
    pid = admin_data['patient_id']
    at = datetime(2026, 9, 29, 0, 40)
    source_ids = []
    for index in range(4):
        row = DeviceRawData(clinician_id=admin_scope['doctor_a']['id'], patient_id=pid,
            device_id=admin_data['device_id'], foot='L' if index % 2 == 0 else 'R',
            collected_at=at, uploaded_at=at, **{f'p{i}': 100.0 for i in range(1, 10)},
            ax=1, ay=2, az=3, gx=4, gy=5, gz=6, step_length=.6, walking_speed=1.2,
            single_support_time=.4, double_support_time=.2)
        db.session.add(row)
        db.session.flush()
        source_ids.append(row.id)
    db.session.commit()
    response = client.post(f'/patients/{pid}/gait/sessions/{_session_id(pid, at)}/snapshots:ensure',
                           headers=admin_scope['admin']['headers'], json={})
    assert response.status_code == 201, response.get_json()
    assert response.get_json()['snapshot_id'] != admin_data['snapshot_id']
    owners = db.session.query(DeviceRawData.clinician_id).filter(DeviceRawData.id.in_(source_ids)).all()
    assert owners == [(admin_scope['doctor_a']['id'],)] * 4


@pytest.mark.parametrize('suffix', ['', '/data', '/gait/sessions', '/gait/sessions/{sid}',
                                  '/gait/sessions/{sid}/frames', '/gait/snapshots/{snapshot}',
                                  '/gait/snapshots/{snapshot}/status', '/gait/snapshots/{snapshot}/agent-projection'])
def test_admin_reads_all_workbench_sources_but_doctor_cannot_cross_owner(client, admin_scope, admin_data, suffix):
    suffix = suffix.format(sid=admin_data['session_id'], snapshot=admin_data['snapshot_id'])
    path = f"/patients/{admin_data['patient_id']}" + suffix
    response = client.get(path, headers=admin_scope['admin']['headers'])
    assert response.status_code == 200, response.get_json()
    assert client.get(path, headers=admin_scope['doctor_b']['headers']).status_code == 403


def test_admin_global_scope_does_not_allow_mismatched_snapshot(client, admin_scope, admin_data):
    response = client.get(
        f"/patients/{admin_data['other_patient_id']}/gait/snapshots/{admin_data['snapshot_id']}",
        headers=admin_scope['admin']['headers'])
    assert response.status_code == 404


def test_transaction_scope_uses_admin_database_role_not_request_owner(db, admin_scope, admin_data):
    with AnalysisSnapshotRepository().transaction(actor_id=admin_scope['admin']['id'],
                                                  patient_id=admin_data['patient_id']) as repo:
        assert repo.snapshot(admin_data['snapshot_id'], admin_data['patient_id']).patient_id == admin_data['patient_id']
