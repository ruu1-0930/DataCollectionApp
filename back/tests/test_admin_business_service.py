"""Administrator snapshot browsing never enters revision or publication writes."""

from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import event
from models.models import AnalysisSnapshot, DeviceRawData


def test_saved_read_does_not_refresh_late_source_or_emit_dml(client, db, admin_scope, admin_data):
    original = db.session.get(DeviceRawData, admin_data['raw_ids'][0])
    fields = {column.name: getattr(original, column.name) for column in DeviceRawData.__table__.columns
              if column.name != 'id'}
    fields['collected_at'] += timedelta(seconds=1)
    fields['uploaded_at'] += timedelta(seconds=1)
    db.session.add(DeviceRawData(**fields))
    db.session.commit()
    statements = []

    def observe(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().split(' ', 1)[0].upper() in {'INSERT', 'UPDATE', 'DELETE'}:
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', observe)
    try:
        response = client.get(f"/admin/patients/{admin_data['patient_id']}/gait/snapshots/{admin_data['snapshot_id']}",
                              headers=admin_scope['admin']['headers'])
    finally:
        event.remove(db.engine, 'before_cursor_execute', observe)
    assert response.status_code == 200
    assert response.get_json()['data']['source_check'] == 'not_performed'
    assert response.get_json()['data']['snapshot']['state'] == 'published'
    assert statements == []


def test_corrupt_stored_payload_fails_without_rebuilding(client, db, admin_scope, admin_data):
    original = db.session.get(AnalysisSnapshot, admin_data['snapshot_id'])
    values = {column.name: getattr(original, column.name) for column in AnalysisSnapshot.__table__.columns}
    corrupt_id = str(uuid4())
    values.update(id=corrupt_id, analyzer_set_version='synthetic-corrupt',
                  identity_fingerprint=uuid4().hex * 2, canonical_payload='{"broken":true}')
    db.session.add(AnalysisSnapshot(**values))
    db.session.commit()
    before = AnalysisSnapshot.query.count()
    response = client.get(f"/admin/patients/{admin_data['patient_id']}/gait/snapshots/{corrupt_id}",
                          headers=admin_scope['admin']['headers'])
    assert response.status_code == 503
    assert AnalysisSnapshot.query.count() == before
    assert 'broken' not in response.get_data(as_text=True)


def test_session_gap_keeps_exact_microseconds_and_inclusive_end_date(client, db, admin_scope, admin_data):
    original = db.session.get(DeviceRawData, admin_data['raw_ids'][0])
    values = {c.name: getattr(original, c.name) for c in DeviceRawData.__table__.columns if c.name != 'id'}
    for delta in (timedelta(seconds=30), timedelta(seconds=60, microseconds=1)):
        db.session.add(DeviceRawData(**(values | {'collected_at': original.collected_at + delta})))
    db.session.commit()
    response = client.get(f"/admin/patients/{admin_data['patient_id']}/gait/sessions?end=2026-09-29",
                          headers=admin_scope['admin']['headers'])
    assert response.status_code == 200
    result = response.get_json()['data']
    assert result['total'] == 2
    assert [row['row_count'] for row in result['items']] == [1, 5]


def test_nonfinite_raw_is_explicitly_unavailable_not_zero(client, db, admin_scope, admin_data):
    original = db.session.get(DeviceRawData, admin_data['raw_ids'][-1])
    original.ax = float('inf')
    db.session.commit()
    response = client.get(f"/admin/patients/{admin_data['patient_id']}/raw-data", headers=admin_scope['admin']['headers'])
    assert response.status_code == 200
    row = response.get_json()['data']['items'][0]
    assert row['ax'] is None and 'ax' in row['unavailable_fields']
    assert db.session.get(DeviceRawData, original.id).ax == float('inf')
