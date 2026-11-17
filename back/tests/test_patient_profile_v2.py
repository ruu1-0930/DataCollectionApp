"""Synthetic SQLite coverage for patient-profile V2 and registration boundaries."""
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from models.models import Clinician, CollectionSession, Patient, PatientPII


def profile(**changes):
    return {'name': ' synthetic patient ', 'phone': None, 'gender': '女', 'age': 65,
            'height_cm': 162.5, 'weight_kg': 55, 'shoe_size_eu': 38.5, **changes}


def headers(scope, key='doctor_a'):
    return scope[key]['headers']


def create(client, scope, payload=None, key='doctor_a'):
    return client.post('/v2/patients', headers=headers(scope, key),
                       json=profile() if payload is None else payload)


def test_empty_phone_does_not_merge_same_name_patients(client, admin_scope, db):
    first = create(client, admin_scope)
    second = create(client, admin_scope)
    assert first.status_code == second.status_code == 200
    a, b = first.get_json()['data'], second.get_json()['data']
    assert a['id'] != b['id']
    assert a['subject_id'] != b['subject_id']
    assert a['existed'] is b['existed'] is False
    assert a['name'] == b['name'] == 'synthetic patient'
    assert db.session.get(PatientPII, a['id']).phone is None
    assert db.session.get(PatientPII, b['id']).phone is None
    assert CollectionSession.query.count() == 0


@pytest.mark.parametrize('phone', [None, '', '   ', '\t\n'])
def test_optional_phone_normalizes_to_sql_null(client, admin_scope, db, phone):
    response = create(client, admin_scope, profile(phone=phone))
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['phone'] is None
    assert db.session.get(PatientPII, data['id']).phone is None


def test_omitted_phone_and_nonempty_phone_dedup_only_within_owner(client, admin_scope):
    payload = profile()
    del payload['phone']
    assert create(client, admin_scope, payload).status_code == 200
    first = create(client, admin_scope, profile(phone='13900000000')).get_json()['data']
    duplicate = create(client, admin_scope, profile(name='other', phone='13900000000')).get_json()['data']
    other = create(client, admin_scope, profile(phone='13900000000'), 'doctor_b').get_json()['data']
    assert duplicate['id'] == first['id']
    assert duplicate['name'] == 'synthetic patient'
    assert duplicate['existed'] is True
    assert other['id'] != first['id']


def test_update_keeps_identity_even_when_phone_matches_another_patient(client, admin_scope):
    a = create(client, admin_scope).get_json()['data']
    b = create(client, admin_scope, profile(phone='13900000000')).get_json()['data']
    response = client.put(f"/v2/patients/{a['id']}/profile", headers=headers(admin_scope),
                          json=profile(name=' updated ', phone='13900000000', height_cm=175))
    assert response.status_code == 200
    updated = response.get_json()['data']
    assert updated['id'] == a['id'] != b['id']
    assert updated['subject_id'] == a['subject_id']
    assert updated['name'] == 'updated'
    assert updated['height_cm'] == 175
    assert client.get(f"/v2/patients/{a['id']}/profile", headers=headers(admin_scope)).get_json()['data'] == updated


def test_scope_database_role_refresh_admin_update_and_no_admin_create(client, admin_scope, db):
    data = create(client, admin_scope).get_json()['data']
    url = f"/v2/patients/{data['id']}/profile"
    for method in ('get', 'put'):
        kwargs = {'json': profile()} if method == 'put' else {}
        assert getattr(client, method)(url, headers=headers(admin_scope, 'doctor_b'), **kwargs).status_code == 403
        assert getattr(client, method)(url, headers=headers(admin_scope, 'admin'), **kwargs).status_code == 200
    assert create(client, admin_scope, key='admin').status_code == 403
    db.session.get(Clinician, admin_scope['admin']['id']).role = 'clinician'
    db.session.commit()
    assert client.put(url, headers=headers(admin_scope, 'admin'), json=profile()).status_code == 403
    assert client.get('/v2/patients/999/profile', headers=headers(admin_scope)).status_code == 404
    assert client.get(url).status_code == 401


@pytest.mark.parametrize('field,value', [
    ('name', ''), ('name', '  '), ('name', 'a' * 51), ('name', 7),
    ('phone', '123'), ('phone', 13900000000), ('phone', '13900000000\n'),
    ('gender', 'M'), ('gender', None), ('gender', ['女']),
    ('age', -1), ('age', 151), ('age', 65.5), ('age', True), ('age', None),
    *[(field, value) for field in ('height_cm', 'weight_kg', 'shoe_size_eu')
      for value in (None, 0, -1, float('nan'), float('inf'), float('-inf'), True, '60')],
    ('height_cm', 300.1), ('height_cm', 10 ** 400), ('weight_kg', 1000.1),
    ('shoe_size_eu', 100.5), ('shoe_size_eu', 38.25),
])
def test_invalid_profile_is_rejected_without_writes(client, admin_scope, field, value):
    response = create(client, admin_scope, profile(**{field: value}))
    assert response.status_code == 400
    assert Patient.query.count() == 0


@pytest.mark.parametrize('field', ['name', 'gender', 'age', 'height_cm', 'weight_kg', 'shoe_size_eu'])
def test_required_profile_fields(client, admin_scope, field):
    payload = profile()
    del payload[field]
    assert create(client, admin_scope, payload).status_code == 400


@pytest.mark.parametrize('payload', [[], None, {}, {'unexpected': 'field'}])
def test_strict_request_object(client, admin_scope, payload):
    assert create(client, admin_scope, payload if payload is not None else []).status_code == 400
    assert create(client, admin_scope, {**profile(), 'extra': 1}).status_code == 400
    assert client.post('/v2/patients', headers={**headers(admin_scope), 'Content-Type': 'application/json'},
                       data='{broken').status_code == 400


@pytest.mark.parametrize('age', [0, 150])
def test_wide_input_boundaries_are_not_medical_thresholds(client, admin_scope, age):
    response = create(client, admin_scope, profile(name='a' * 50, age=age, height_cm=300,
                                                 weight_kg=1000, shoe_size_eu=100))
    assert response.status_code == 200
    assert response.get_json()['data']['age'] == age


def test_positive_small_body_values_and_half_eu_size_are_allowed(client, admin_scope):
    response = create(client, admin_scope, profile(height_cm=0.1, weight_kg=0.1, shoe_size_eu=0.5))
    assert response.status_code == 200
    assert response.get_json()['data']['shoe_size_eu'] == 0.5


def test_legacy_profile_read_preserves_gender_and_missing_fields(client, admin_scope):
    old = client.post('/patients', headers=headers(admin_scope),
                      json={'name': 'old', 'phone': '13700000000', 'gender': 'M'}).get_json()['data']
    read = client.get(f"/v2/patients/{old['id']}/profile", headers=headers(admin_scope))
    assert read.status_code == 200
    data = read.get_json()['data']
    assert data['gender'] == 'M'
    assert data['height_cm'] is data['weight_kg'] is data['shoe_size_eu'] is None
    assert set(old) == {'id', 'subject_id', 'gender', 'age', 'name', 'phone', 'last_collected_at', 'existed'}


@pytest.mark.parametrize('phone', [None, '', '   '])
def test_doctor_phone_remains_required(client, phone):
    response = client.post('/clinician/enable', json={
        'hospital': 'synthetic', 'dept': 'D', 'name': 'synthetic', 'phone': phone, 'passcode': '1234'})
    assert response.status_code == 400


def validator(filename, definition=None):
    document = json.loads((Path(__file__).parents[1] / 'contracts' / filename).read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(document)
    return Draft202012Validator({**document, **({'$ref': '#/$defs/' + definition} if definition else {})})


def test_profile_and_registration_contracts_are_strict_and_snapshot_excludes_phone(client, admin_scope):
    input_validator = validator('patient_profile_v2.schema.json', 'PatientProfileInputV2')
    input_validator.validate(profile())
    output_validator = validator('patient_profile_v2.schema.json', 'PatientProfileV2')
    data = create(client, admin_scope).get_json()['data']
    output_validator.validate(data)
    registration_validator = validator('collection_registration_v1.schema.json')
    registration = {'schema_version': 1, 'patient_id': data['id'], 'patient_snapshot': {
        'name': 'synthetic patient', 'gender': '女', 'age': 65, 'height_cm': 162.5,
        'weight_kg': 55, 'shoe_size_eu': 38.5}, 'test_type': 'walk_10m_usual', 'remarks': ''}
    for test_type in ('static_standing', 'walk_10m_usual', 'five_times_sit_to_stand', 'tug', 'free_capture'):
        registration_validator.validate({**registration, 'test_type': test_type})
    for changes in ({'test_type': 'legacy_unspecified'}, {'remarks': 'a' * 2001}, {'extra': 1},
                    {'patient_snapshot': {**registration['patient_snapshot'], 'phone': None}}):
        with pytest.raises(ValidationError):
            registration_validator.validate({**registration, **changes})
    with pytest.raises(ValidationError):
        input_validator.validate({**profile(), 'extra': 1})


def test_service_rechecks_actor_and_keeps_saves_separate_from_capture(client, admin_scope, db):
    from access import AccessError, AccountContext
    from services.patient_profile import PatientProfileService
    service = PatientProfileService()
    actor = AccountContext(admin_scope['doctor_a']['id'], 'admin')
    created = service.create(actor, profile())
    assert service.get(actor, created['id'])['name'] == 'synthetic patient'
    assert service.update(actor, created['id'], profile(name='edited'))['name'] == 'edited'
    foreign = AccountContext(admin_scope['doctor_b']['id'], 'admin')
    with pytest.raises(AccessError):
        service.update(foreign, created['id'], profile())
    assert CollectionSession.query.count() == 0


def test_invalid_update_is_atomic_and_does_not_change_frozen_registration(client, admin_scope, db):
    from datetime import datetime
    from models.models import Device
    created = create(client, admin_scope).get_json()['data']
    device = Device(clinician_id=admin_scope['doctor_a']['id'], device_code='synthetic-device')
    db.session.add(device)
    db.session.flush()
    frozen = '{"patient_snapshot":{"name":"original"}}'
    capture = CollectionSession(capture_id='00000000-0000-4000-8000-000000000001',
        clinician_id=admin_scope['doctor_a']['id'], patient_id=created['id'], device_id=device.id,
        mobile_started_at=datetime(2026, 11, 18), server_created_at=datetime(2026, 11, 18),
        metadata_schema_version=1, test_type='static_standing', registration_json=frozen,
        registration_hash='a' * 64)
    db.session.add(capture)
    db.session.commit()
    url = f"/v2/patients/{created['id']}/profile"
    assert client.put(url, headers=headers(admin_scope), json=profile(name='changed', age=-1)).status_code == 400
    assert client.get(url, headers=headers(admin_scope)).get_json()['data']['name'] == 'synthetic patient'
    assert client.put(url, headers=headers(admin_scope), json=profile(name='changed')).status_code == 200
    db.session.refresh(capture)
    assert capture.registration_json == frozen
    assert capture.registration_hash == 'a' * 64
    assert capture.final_counts_json is capture.finalization_state is None
