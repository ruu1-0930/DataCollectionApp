"""Access events identify the real administrator without copying patient data."""

import json


def test_query_log_retains_actor_and_trace_but_not_patient_fields(client, admin_scope, admin_data, caplog):
    trace = '00000000-0000-4000-8000-000000000001'
    response = client.get(f"/admin/patients/{admin_data['patient_id']}",
        headers={**admin_scope['admin']['headers'], 'X-Trace-ID': trace})
    assert response.status_code == 200
    assert response.headers['X-Trace-ID'] == trace
    records = [json.loads(record.message) for record in caplog.records if record.name == 'sarcogait.admin']
    assert records[-1]['actor_id'] == admin_scope['admin']['id']
    assert records[-1]['owner_clinician_id'] == admin_scope['doctor_a']['id']
    assert records[-1]['trace_id'] == trace
    assert '13900000000' not in json.dumps(records)
    assert 'synthetic-patient' not in json.dumps(records)
