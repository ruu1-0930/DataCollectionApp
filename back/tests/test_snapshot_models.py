"""Persistence/DTO contracts only: synthetic SQLite, never a clinical database."""

import copy
import datetime
import json
from pathlib import Path

import pytest
from flask import Flask
from jsonschema import Draft202012Validator
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

from config import db
from models.models import (
    Clinician, Device, Patient, DeviceRawData, GaitSessionRevision,
    SnapshotBuildAttempt, AnalysisSnapshot, AgentSnapshotProjection,
    SnapshotPublicationClaim, ClinicalAuditEvent, IntegrationOutbox,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime.datetime(2026, 9, 27, 0, 0)
UUID = '00000000-0000-4000-8000-000000000001'
OTHER = '00000000-0000-4000-8000-000000000002'
HASH = 'a' * 64
MODELS = (GaitSessionRevision, SnapshotBuildAttempt, AnalysisSnapshot,
          AgentSnapshotProjection, SnapshotPublicationClaim,
          ClinicalAuditEvent, IntegrationOutbox)


@pytest.fixture
def store():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        db.session.execute(text('PRAGMA foreign_keys=ON'))
        assert db.session.execute(text('PRAGMA foreign_keys')).scalar() == 1
        db.create_all()
        c = Clinician(hospital='synthetic', dept='D', name='fixture', phone='0', passcode_hash='x')
        db.session.add(c)
        db.session.flush()
        p = Patient(clinician_id=c.id, subject_id='#synthetic')
        d = Device(clinician_id=c.id, device_code='synthetic')
        db.session.add_all([p, d])
        db.session.flush()
        raw = DeviceRawData(device_id=d.id, patient_id=p.id, clinician_id=c.id, foot='L',
                            **{f'p{i}': 1 for i in range(1, 10)},
                            ax=1, ay=1, az=1, gx=1, gy=1, gz=1, step_length=1,
                            walking_speed=1, single_support_time=1, double_support_time=1)
        db.session.add(raw)
        db.session.flush()
        other_raw = DeviceRawData(**{
            column.name: getattr(raw, column.name)
            for column in DeviceRawData.__table__.columns if column.name != 'id'
        })
        db.session.add(other_raw)
        db.session.flush()
        revision = GaitSessionRevision(
            id=UUID, patient_id=p.id, device_id=d.id, session_key='synthetic-session',
            revision=1, state='closed_by_inactivity', ordered_row_ids_canonical='[1]',
            first_row_id=raw.id, last_row_id=raw.id, row_count=1, last_accepted_row_id=raw.id,
            event_start_at=NOW, event_end_at=NOW, ingest_start_at=NOW, ingest_end_at=NOW,
            closure_policy_version='gap-v1', closure_evidence_canonical='{}', closed_at=NOW)
        db.session.add(revision)
        db.session.flush()
        snapshot = AnalysisSnapshot(
            id=UUID, patient_id=p.id, session_revision_id=UUID, raw_data_fingerprint=HASH,
            identity_fingerprint=HASH, snapshot_schema_version='1', analyzer_set_version='1',
            threshold_profile_version='1', canonical_payload='{}', content_hash=HASH,
            state='published', state_version=1, created_at=NOW, published_at=NOW)
        db.session.add(snapshot)
        db.session.commit()
        yield {'patient': p.id, 'device': d.id, 'actor': c.id,
               'raw': raw.id, 'other_raw': other_raw.id}
        db.session.remove()
        db.drop_all()


def records(scope):
    return {
        GaitSessionRevision: dict(id=OTHER, patient_id=scope['patient'], device_id=scope['device'],
            session_key='second-session', revision=1, state='collecting', ordered_row_ids_canonical='[1]',
            first_row_id=scope['raw'], last_row_id=scope['raw'], row_count=1,
            last_accepted_row_id=scope['raw'], event_start_at=NOW, event_end_at=NOW,
            ingest_start_at=NOW, ingest_end_at=NOW, closure_policy_version='gap-v1'),
        SnapshotBuildAttempt: dict(id=OTHER, identity_fingerprint=HASH, attempt_number=1,
            state='pending', trace_id=OTHER, created_at=NOW),
        AnalysisSnapshot: dict(id=OTHER, patient_id=scope['patient'], session_revision_id=UUID,
            raw_data_fingerprint='b'*64, identity_fingerprint='b'*64,
            snapshot_schema_version='1', analyzer_set_version='1', threshold_profile_version='1',
            canonical_payload='{}', content_hash=HASH, state='published', state_version=1,
            created_at=NOW, published_at=NOW),
        AgentSnapshotProjection: dict(snapshot_id=UUID, projection_schema_version='1',
            canonical_payload='{}', content_hash=HASH, created_at=NOW),
        SnapshotPublicationClaim: dict(id=OTHER, snapshot_id=UUID, state_version=1,
            workflow_run_id=OTHER, candidate_hash=HASH, actor_id=scope['actor'], claimed_at=NOW),
        ClinicalAuditEvent: dict(id=OTHER, trace_id=OTHER, actor_id=scope['actor'],
            patient_id=scope['patient'], snapshot_id=UUID, session_revision_id=UUID,
            action='snapshot.read', result='success', canonical_payload='{}', event_hash=HASH,
            created_at=NOW),
        IntegrationOutbox: dict(event_type='snapshot.superseded', event_version='1',
            snapshot_id=UUID, patient_id=scope['patient'], state_version=1,
            canonical_payload='{}', content_hash=HASH, created_at=NOW),
    }


@pytest.mark.parametrize('model', MODELS)
def test_every_record_can_be_persisted(store, model):
    row = model(**records(store)[model])
    db.session.add(row)
    db.session.commit()
    assert db.session.get(model, inspect(row).identity) is row


@pytest.mark.parametrize('model,field', [(model, fk.parent.name)
    for model in MODELS for fk in model.__table__.foreign_keys])
def test_every_foreign_key_is_enforced(store, model, field):
    values = records(store)[model]
    values[field] = 999999 if isinstance(model.__table__.c[field].type, db.Integer) else 'f'*36
    db.session.add(model(**values))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_snapshot_rejects_valid_revision_belonging_to_another_patient(store):
    other_patient = Patient(clinician_id=store['actor'], subject_id='#other-synthetic')
    db.session.add(other_patient)
    db.session.commit()
    values = records(store)[AnalysisSnapshot]
    values['patient_id'] = other_patient.id
    # Both patient ID and revision ID exist; only the pair is invalid.
    assert db.session.get(Patient, other_patient.id)
    assert db.session.get(GaitSessionRevision, UUID)
    db.session.add(AnalysisSnapshot(**values))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


FROZEN_REVISION_FIELDS = (
    ('ordered_row_ids_canonical', '[1,2]'),
    ('first_row_id', 'other_raw'), ('last_row_id', 'other_raw'),
    ('row_count', 2), ('last_accepted_row_id', 'other_raw'),
    ('event_start_at', NOW + datetime.timedelta(seconds=1)),
    ('event_end_at', NOW + datetime.timedelta(seconds=1)),
    ('ingest_start_at', NOW + datetime.timedelta(seconds=1)),
    ('ingest_end_at', NOW + datetime.timedelta(seconds=1)),
    ('closure_policy_version', 'other-policy'),
    ('closure_evidence_canonical', '{"changed":true}'),
    ('closed_at', NOW + datetime.timedelta(seconds=1)),
)


@pytest.mark.parametrize('state', ['closed_by_inactivity', 'superseded'])
@pytest.mark.parametrize('field,value', FROZEN_REVISION_FIELDS)
def test_closed_or_superseded_revision_rejects_bulk_evidence_rewrite(store, state, field, value):
    if state == 'superseded':
        db.session.execute(text('UPDATE gait_session_revision SET state=:state WHERE id=:id'),
                           {'state': state, 'id': UUID})
        db.session.commit()
    if value == 'other_raw':
        value = store['other_raw']  # valid FK, so failure proves the freeze trigger
    with pytest.raises(IntegrityError):
        db.session.execute(text(f'UPDATE gait_session_revision SET {field}=:value WHERE id=:id'),
                           {'value': value, 'id': UUID})
        db.session.commit()
    db.session.rollback()


def test_collecting_revision_can_build_evidence_then_cannot_reopen(store):
    db.session.add(GaitSessionRevision(**records(store)[GaitSessionRevision]))
    db.session.commit()
    db.session.execute(text('UPDATE gait_session_revision SET ordered_row_ids_canonical=:rows, '
                            'row_count=2 WHERE id=:id'), {'rows': '[1,2]', 'id': OTHER})
    db.session.commit()
    db.session.execute(text("UPDATE gait_session_revision SET state='closed_by_inactivity', "
                            'closure_evidence_canonical=:evidence, closed_at=:closed WHERE id=:id'),
                       {'evidence': '{}', 'closed': NOW, 'id': OTHER})
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(text("UPDATE gait_session_revision SET state='collecting' WHERE id=:id"),
                           {'id': OTHER})
        db.session.commit()
    db.session.rollback()


def test_revision_identity_is_immutable_even_while_collecting(store):
    db.session.add(GaitSessionRevision(**records(store)[GaitSessionRevision]))
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(text('UPDATE gait_session_revision SET session_key=:key WHERE id=:id'),
                           {'key': 'rewritten-key', 'id': OTHER})
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('model', [GaitSessionRevision, SnapshotBuildAttempt, AnalysisSnapshot])
def test_invalid_state_rejected_by_database_even_without_orm(store, model):
    values = records(store)[model]
    values['state'] = 'complete'
    fields = ', '.join(values)
    params = ', '.join(':' + key for key in values)
    with pytest.raises(IntegrityError):
        db.session.execute(text(f'INSERT INTO {model.__tablename__} ({fields}) VALUES ({params})'), values)
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('model', [GaitSessionRevision, SnapshotBuildAttempt,
                                  AnalysisSnapshot, AgentSnapshotProjection, SnapshotPublicationClaim])
def test_unique_identity_is_enforced(store, model):
    values = records(store)[model]
    db.session.add(model(**values))
    db.session.commit()
    duplicate = dict(values)
    if 'id' in duplicate:
        duplicate['id'] = '00000000-0000-4000-8000-000000000003'
    db.session.add(model(**duplicate))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_snapshot_identity_tuple_not_just_fingerprint(store):
    values = records(store)[AnalysisSnapshot]
    values['raw_data_fingerprint'] = HASH
    values['identity_fingerprint'] = 'b'*64
    db.session.add(AnalysisSnapshot(**values))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('model,field', [(m, f) for m in MODELS for f in (
    ['canonical_payload', 'content_hash'] if 'content_hash' in m.__table__.c
    else ['canonical_payload', 'event_hash'] if m is ClinicalAuditEvent else [])])
def test_payload_and_hash_are_separate_non_nullable_columns(store, model, field):
    values = records(store)[model]
    values[field] = None
    db.session.add(model(**values))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('model', [AnalysisSnapshot, AgentSnapshotProjection, IntegrationOutbox])
@pytest.mark.parametrize('field,value', [
    ('canonical_payload', '{"changed":true}'), ('canonical_payload', '{"A":1}'),
    ('canonical_payload', '{} '), ('content_hash', 'b'*64)])
def test_immutable_content_rejects_bulk_sql_update(store, model, field, value):
    if model is not AnalysisSnapshot:
        db.session.add(model(**records(store)[model]))
        db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(text(f'UPDATE {model.__tablename__} SET {field}=:value'), {'value': value})
        db.session.commit()
    db.session.rollback()


def test_lifecycle_updates_leave_canonical_payload_untouched(store):
    row = db.session.get(AnalysisSnapshot, UUID)
    row.state = 'superseded'
    row.state_version = 2
    row.superseded_at = NOW
    db.session.commit()
    assert row.canonical_payload == '{}' and row.content_hash == HASH
    with pytest.raises(IntegrityError):
        db.session.execute(text('UPDATE analysis_snapshot SET state_version=1'))
        db.session.commit()
    db.session.rollback()


@pytest.mark.parametrize('statement', ['UPDATE clinical_audit_event SET result=\'changed\'',
                                     'DELETE FROM clinical_audit_event'])
def test_audit_is_append_only_for_bulk_sql(store, statement):
    db.session.add(ClinicalAuditEvent(**records(store)[ClinicalAuditEvent]))
    db.session.commit()
    with pytest.raises(IntegrityError):
        db.session.execute(text(statement))
        db.session.commit()
    db.session.rollback()


def test_outbox_ids_are_monotonic(store):
    first = IntegrationOutbox(**records(store)[IntegrationOutbox])
    db.session.add(first)
    db.session.commit()
    second = IntegrationOutbox(**records(store)[IntegrationOutbox])
    db.session.add(second)
    db.session.commit()
    assert second.id > first.id


@pytest.mark.parametrize('model,field', [
    (GaitSessionRevision, 'revision'), (GaitSessionRevision, 'row_count'),
    (SnapshotBuildAttempt, 'attempt_number'), (AnalysisSnapshot, 'state_version'),
    (SnapshotPublicationClaim, 'state_version'), (IntegrationOutbox, 'state_version'),
])
@pytest.mark.parametrize('bad_value', [0, -1])
def test_positive_fields_reject_zero_and_negative_bulk_insert(store, model, field, bad_value):
    values = records(store)[model]
    values[field] = bad_value
    fields = ', '.join(values)
    params = ', '.join(':' + key for key in values)
    with pytest.raises(IntegrityError):
        db.session.execute(text(f'INSERT INTO {model.__tablename__} ({fields}) VALUES ({params})'), values)
        db.session.commit()
    db.session.rollback()


def schema():
    return json.loads((ROOT / 'contracts/gait_snapshot_v1.schema.json').read_text(encoding='utf-8'))


def validator(name):
    document = schema()
    return Draft202012Validator({**document, '$ref': '#/$defs/' + name})


METRICS = [('walking_speed_mps', 'm/s', 'firmware'), ('step_length_m', 'm', 'firmware'),
    ('single_support_time_s', 's', 'firmware'), ('double_support_time_s', 's', 'firmware'),
    ('cadence_spm', 'steps/min', 'derived'), ('step_length_asymmetry_pct', '%', 'derived'),
    ('stride_time_cv_pct', '%', 'derived'), ('double_support_ratio_pct', '%', 'derived')]


def metric(key='walking_speed_mps', unit='m/s', source='firmware'):
    return dict(evidence_id='metric.' + key, metric_id=key, value_decimal='1.000000', unit=unit,
                source=source, left_value_decimal=None, right_value_decimal=None,
                statistics=dict(n=1, mean_decimal='1.000000', median_decimal='1.000000',
                                std_decimal='0.000000', cv_pct_decimal='0.000000'),
                formula=None if source == 'firmware' else 'synthetic formula',
                source_field=key if source == 'firmware' else None,
                evidence_level='firmware_measurement' if source == 'firmware' else 'exploratory',
                reason_codes=[])


def projection():
    return dict(projection_schema_version='1', projection_content_hash=HASH,
        snapshot_id=UUID, snapshot_content_hash=HASH, snapshot_state_version=1,
        patient_id=1, session_id='synthetic-session',
        provenance=dict(snapshot_schema_version='1', analyzer_set_version='1',
                        threshold_profile_version='1', closure_policy_version='gap-v1'),
        data_quality=dict(status='complete', gate='eligible', total_frames=1, paired_frames=1,
                          paired_frame_rate_pct_decimal='100.000000', missing_required_values=0,
                          reason_codes=[]), exclusions=[], flags=[],
        metrics=[metric(*args) for args in METRICS], pressure_summary=None,
        evidence_index=[dict(evidence_id='metric.walking_speed_mps', field_path='/metrics/0')],
        analyzer_statuses=dict(spatiotemporal='success', data_quality='success', pressure='empty'),
        limitations=['synthetic_only', 'pressure_adc_uncalibrated'])


def full_snapshot():
    result = projection()
    for field in ('projection_schema_version', 'projection_content_hash', 'snapshot_content_hash'):
        result.pop(field)
    result.update(schema_version='1', content_hash=HASH, session_revision_id=UUID,
        state='published', created_at='2026-09-27T00:00:00.000Z',
        session=dict(start_at='2026-09-27T00:00:00.000Z', end_at='2026-09-27T00:00:00.000Z',
            first_row_id=1, last_row_id=1, row_count=1,
            last_accepted_row_id=1, raw_data_fingerprint=HASH,
            closure=dict(state='closed_by_inactivity', closed_at='2026-09-27T00:00:30.000Z',
                policy_version='gap-v1', gap_ms=30000, reason='device_quiet_period',
                evidence_at='2026-09-27T00:00:30.000Z', next_row_id=None)),
        chart_series=[])
    return result


@pytest.mark.parametrize('name,payload', [
    ('MetricEvidenceV1', metric()), ('AgentSnapshotProjectionV1', projection()),
    ('AnalysisSnapshotV1', full_snapshot()),
    ('SnapshotPublicationClaimV1', dict(claim_id=UUID, snapshot_id=UUID, snapshot_state_version=1,
        workflow_run_id=OTHER, candidate_hash=HASH, actor_id=1, claimed_at='2026-09-27T00:00:00.000Z')),
    ('ErrorEnvelopeV1', dict(error=dict(code='stale_snapshot', message='Snapshot no longer current.',
        trace_id=None, retryable=False, details=dict(replacement_snapshot_available=True)))),
])
def test_positive_dto_examples(name, payload):
    validator(name).validate(payload)


def test_schema_is_valid_and_every_object_is_closed():
    Draft202012Validator.check_schema(schema())
    def walk(value):
        if isinstance(value, dict):
            if value.get('type') == 'object':
                assert value.get('additionalProperties') is False
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(schema())


@pytest.mark.parametrize('change', [
    {'value_decimal': 'NaN'}, {'value_decimal': 'Infinity'}, {'value_decimal': '1e2'},
    {'value_decimal': 1.0}, {'value_decimal': '1.0'}, {'value_decimal': '-0.000000'},
    {'value_decimal': None}, {'metric_id': 'stride_length_m'}, {'unit': 'cm'}, {'source': 'derived'},
    {'unexpected': True}, {'statistics': {'n': 1, 'secret': 'x'}},
])
def test_metric_rejects_invalid_or_ambiguous_evidence(change):
    payload = metric()
    payload.update(change)
    assert list(validator('MetricEvidenceV1').iter_errors(payload))


def test_null_metric_has_explicit_quality_reason():
    payload = metric()
    payload.update(value_decimal=None, reason_codes=['missing_required_values'])
    validator('MetricEvidenceV1').validate(payload)


@pytest.mark.parametrize('name,builder', [('AnalysisSnapshotV1', full_snapshot),
                                        ('AgentSnapshotProjectionV1', projection)])
def test_exactly_eight_distinct_metric_ids(name, builder):
    payload = builder()
    payload['metrics'][-1] = copy.deepcopy(payload['metrics'][0])
    payload['metrics'][-1]['evidence_id'] = 'a-different-evidence-id'
    assert list(validator(name).iter_errors(payload))
    payload['metrics'].pop()
    assert list(validator(name).iter_errors(payload))


@pytest.mark.parametrize('field', ['chart_series', 'time_series', 'raw_rows', 'frame_id',
                                  'row_id', 'device_id', 'pagination', 'imu', 'name'])
def test_projection_rejects_forbidden_fields(field):
    payload = projection()
    payload[field] = []
    assert list(validator('AgentSnapshotProjectionV1').iter_errors(payload))
    payload = projection()
    payload['metrics'][0][field] = []
    assert list(validator('AgentSnapshotProjectionV1').iter_errors(payload))


@pytest.mark.parametrize('field,value', [('snapshot_id', UUID.upper().replace('000001', 'ABCDEF')),
    ('snapshot_content_hash', 'A'*64), ('snapshot_state_version', 0)])
def test_projection_identity_formats(field, value):
    payload = projection()
    payload[field] = value
    assert list(validator('AgentSnapshotProjectionV1').iter_errors(payload))


def test_error_details_are_bounded_closed_and_safe_codes_only():
    payload = dict(error=dict(code='stale_snapshot', message='safe', trace_id=None,
                             retryable=False, details={'patient_name': 'secret'}))
    assert list(validator('ErrorEnvelopeV1').iter_errors(payload))
    payload['error'].update(code='unlisted_error', details={})
    assert list(validator('ErrorEnvelopeV1').iter_errors(payload))


def test_pressure_aggregate_has_only_closed_aggregate_sensor_statistics():
    sensor = dict(mean_adc_decimal='1.000000', valid_samples=3, total_samples=3)
    side = dict(sensors={f'p{i}': dict(sensor) for i in range(1, 10)})
    pressure = dict(method='nonzero_mean_v1', unit='ADC', threshold_profile='synthetic',
        left=side, right=copy.deepcopy(side), matched_sensors={}, matched_sensor_count=0,
        left_load_proxy_adc_decimal=None, right_load_proxy_adc_decimal=None,
        left_load_share_pct_decimal=None, right_load_share_pct_decimal=None,
        load_asymmetry_pct_decimal=None,
        attention=dict(level=None, quality='insufficient', reason_codes=['insufficient_pressure_data']),
        limitation='pressure_adc_uncalibrated')
    payload = projection()
    payload['pressure_summary'] = pressure
    validator('AgentSnapshotProjectionV1').validate(payload)
    pressure['left']['sensors']['p1']['frame_id'] = 5
    assert list(validator('AgentSnapshotProjectionV1').iter_errors(payload))


def test_mysql_dialect_ddl_and_migration_mirror():
    migration = (ROOT / 'migrations/002_gait_snapshot_v1.sql').read_text(encoding='utf-8')
    greenfield = (ROOT / 'database_schema_mysql.sql').read_text(encoding='utf-8')
    assert migration in greenfield
    assert 'DROP TABLE' not in migration and 'ALTER TABLE device_raw_data' not in migration
    for model in MODELS:
        ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert f'CREATE TABLE {model.__tablename__}' in migration
        assert model.__tablename__ in ddl
        for column in model.__table__.columns:
            assert column.name in migration
    for model in (GaitSessionRevision, SnapshotBuildAttempt, AnalysisSnapshot):
        ddl = str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))
        assert 'ENUM(' in ddl
    assert 'LONGTEXT' in str(CreateTable(AnalysisSnapshot.__table__).compile(dialect=mysql.dialect()))
    assert 'DATETIME(3)' in str(CreateTable(AnalysisSnapshot.__table__).compile(dialect=mysql.dialect()))
    assert 'BINARY NEW.canonical_payload' in migration
    assert 'UNIQUE KEY uq_session_revision_patient (id, patient_id)' in migration
    assert ('FOREIGN KEY (session_revision_id, patient_id) '
            'REFERENCES gait_session_revision(id, patient_id)') in migration
    assert 'trg_gait_session_revision_frozen' in migration
    assert "OLD.state <> 'collecting'" in migration
    assert 'BINARY NEW.closure_evidence_canonical' in migration
    for table in ('gait_session_revision', 'snapshot_build_attempt', 'analysis_snapshot',
                  'snapshot_publication_claim', 'integration_outbox'):
        assert f'trg_{table}_positive_insert' in migration
        assert f'trg_{table}_positive_update' in migration
