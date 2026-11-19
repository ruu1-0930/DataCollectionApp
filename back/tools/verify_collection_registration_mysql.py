"""Operator-only MySQL8 storage acceptance on a fixed disposable verify schema.

One connection, one InnoDB transaction, synthetic UUID-owned rows, final ROLLBACK.
No DDL, application factory, API, model, Agent runtime, production schema or COMMIT.
This checks storage/migration behavior, not HTTP authorization or end-to-end upload.
"""
import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from uuid import uuid4


DATABASE = 'lanya_collection_verify_20261118'
PROTECTED = ('clinical_audit_event', 'device_raw_data', 'device_transformed_data',
             'collection_sessions', 'collection_insole_frames', 'collection_gps_raw',
             'collection_radar_raw', 'collection_radar_targets', 'gait_session_revision',
             'analysis_snapshot', 'agent_snapshot_projection', 'snapshot_publication_claim',
             'integration_outbox', 'snapshot_build_attempt')
TABLES = (*PROTECTED, 'clinicians', 'patients', 'patient_pii', 'devices',
          'data_management_preview', 'data_management_operation', 'data_management_item',
          'data_management_audit_bridge')
EXPORT_TABLES = ('data_export_inventory', 'data_export_grant')
TEST_TYPES = ('static_standing', 'walk_10m_usual', 'five_times_sit_to_stand', 'tug', 'free_capture')
WHEN = datetime(2026, 11, 18, 0, 0, 0)
_phase = 'arguments'


class VerificationFailure(RuntimeError):
    pass


def require(condition):
    if not condition:
        raise VerificationFailure('condition_failed')


def phase(name):
    global _phase
    _phase = name


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(value.encode('utf-8')).hexdigest()


def one(cursor, sql, values=()):
    cursor.execute(sql, values)
    row = cursor.fetchone()
    require(row is not None)
    return row


def insert(cursor, table, values):
    # Every identifier is authored in this file; no operator-supplied SQL identifiers.
    require(table in (*TABLES, *EXPORT_TABLES))
    columns = ','.join('`' + name + '`' for name in values)
    cursor.execute('INSERT INTO `' + table + '` (' + columns + ') VALUES (' +
                   ','.join(['%s'] * len(values)) + ')', tuple(values.values()))
    return cursor.lastrowid


def rejected(cursor, expected, sql, values=()):
    """Retain the same outer transaction even when a negative check unexpectedly succeeds."""
    import pymysql
    cursor.execute('SAVEPOINT expected_failure')
    try:
        try:
            cursor.execute(sql, values)
        except pymysql.MySQLError as error:
            require(error.args and error.args[0] == expected)
        else:
            raise VerificationFailure('expected_rejection_missing')
    finally:
        cursor.execute('ROLLBACK TO SAVEPOINT expected_failure')
        cursor.execute('RELEASE SAVEPOINT expected_failure')


def preflight(cursor, *, verify_export=False):
    require(one(cursor, 'SELECT DATABASE()')[0] == DATABASE)
    version = one(cursor, 'SELECT VERSION()')[0]
    require(version.startswith('8.') and 'mariadb' not in version.lower())
    require(one(cursor, 'SELECT @@foreign_key_checks')[0] == 1)
    require({'STRICT_TRANS_TABLES', 'STRICT_ALL_TABLES'} &
            set(one(cursor, 'SELECT @@sql_mode')[0].split(',')))
    cursor.execute('SELECT table_name,engine FROM information_schema.tables WHERE table_schema=DATABASE()')
    engines = dict(cursor.fetchall())
    require(all(engines.get(name) == 'InnoDB' for name in TABLES))
    if verify_export:
        require(all(engines.get(name) == 'InnoDB' for name in EXPORT_TABLES))
    cursor.execute('SELECT table_name,column_name,is_nullable FROM information_schema.columns '
                   'WHERE table_schema=DATABASE()')
    columns = {(table, column): nullable for table, column, nullable in cursor.fetchall()}
    require(columns.get(('patient_pii', 'phone')) == 'YES')
    for name in ('height_cm', 'weight_kg', 'shoe_size_eu'):
        require(columns.get(('patients', name)) == 'YES')
    for name in ('metadata_schema_version', 'test_type', 'registration_json', 'registration_hash',
                 'final_counts_json', 'finalization_state'):
        require(columns.get(('collection_sessions', name)) == 'YES')
    enum_type = one(cursor, 'SELECT column_type FROM information_schema.columns '
        "WHERE table_schema=DATABASE() AND table_name='gait_session_revision' AND column_name='state'")[0]
    require("'closed_by_capture_stop'" in enum_type)
    cursor.execute('SELECT trigger_name FROM information_schema.triggers WHERE trigger_schema=DATABASE()')
    triggers = {row[0] for row in cursor.fetchall()}
    require({'trg_' + table + '_no_delete' for table in PROTECTED} <= triggers)
    require('trg_clinical_audit_event_no_update' in triggers)


def fixtures(cursor):
    marker = uuid4().hex
    owner = insert(cursor, 'clinicians', dict(hospital='verify-' + marker, dept='synthetic',
        name='synthetic', phone='00000000000', passcode_hash='!not-login', role='clinician'))
    patient = insert(cursor, 'patients', dict(clinician_id=owner, subject_id='cv' + marker[:18],
        gender='男', age=60, height_cm=170, weight_kg=65, shoe_size_eu=40.5))
    insert(cursor, 'patient_pii', dict(patient_id=patient, name='synthetic', phone=None))
    require(one(cursor, 'SELECT phone FROM patient_pii WHERE patient_id=%s', (patient,))[0] is None)
    device = insert(cursor, 'devices', dict(clinician_id=owner, device_code='verify-' + marker,
        device_name='synthetic', is_enabled=1))
    captures = []
    registrations = {}
    for test_type in TEST_TYPES:
        capture = str(uuid4())
        registration = canonical(dict(schema_version=1, patient_id=patient,
            patient_snapshot=dict(name='synthetic', gender='男', age=60, height_cm=170,
                                  weight_kg=65, shoe_size_eu=40.5), test_type=test_type, remarks=''))
        insert(cursor, 'collection_sessions', dict(capture_id=capture, clinician_id=owner,
            patient_id=patient, device_id=device, mobile_started_at=WHEN, server_created_at=WHEN,
            metadata_schema_version=1, test_type=test_type, registration_json=registration,
            registration_hash=digest(registration)))
        row = one(cursor, 'SELECT test_type,registration_json,registration_hash,final_counts_json '
                  'FROM collection_sessions WHERE capture_id=%s', (capture,))
        require(row == (test_type, registration, digest(registration), None))
        captures.append(capture)
        registrations[capture] = registration
    legacy = str(uuid4())
    insert(cursor, 'collection_sessions', dict(capture_id=legacy, clinician_id=owner,
        patient_id=patient, device_id=device, mobile_started_at=WHEN, server_created_at=WHEN))
    require(one(cursor, 'SELECT metadata_schema_version,test_type,registration_json,registration_hash,'
                'final_counts_json,finalization_state FROM collection_sessions WHERE capture_id=%s',
                (legacy,)) == (None,) * 6)
    # Current patient edits must not mutate any frozen registration bytes/hash.
    cursor.execute('UPDATE patients SET height_cm=171 WHERE id=%s AND clinician_id=%s', (patient, owner))
    for capture, registration in registrations.items():
        require(one(cursor, 'SELECT registration_json,registration_hash FROM collection_sessions '
                    'WHERE capture_id=%s', (capture,)) == (registration, digest(registration)))
    return dict(owner=owner, patient=patient, device=device, capture=captures[0],
                sibling=captures[1], legacy=legacy, captures=captures + [legacy])


def event(cursor, table, capture, stream, **payload):
    return insert(cursor, table, dict(capture_id=capture, stream=stream, event_id=str(uuid4()),
        connection_epoch=0, stream_sequence=0, mobile_received_at=WHEN, server_received_at=WHEN,
        payload_hash=digest(stream), **payload))


def storage_cases(cursor, owned, *, verify_patient_purge=False):
    capture = owned['capture']
    raw = []
    for foot in ('L', 'R'):
        values = {name: 1.25 for name in ('p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7', 'p8', 'p9',
            'ax', 'ay', 'az', 'gx', 'gy', 'gz', 'step_length', 'walking_speed',
            'single_support_time', 'double_support_time')}
        raw.append(insert(cursor, 'device_raw_data', dict(device_id=owned['device'], patient_id=owned['patient'],
            clinician_id=owned['owner'], foot=foot, collected_at=WHEN, uploaded_at=WHEN, **values)))
    transformed = insert(cursor, 'device_transformed_data', dict(raw_data_id=raw[0], T1=1, T2=2, T3=3, T4=4, T5=5))
    insole = event(cursor, 'collection_insole_frames', capture, 'insole', left_raw_id=raw[0], right_raw_id=raw[1])
    gps_line = 'GPS1,5,0,nan,nan,nan,nan,0,99.99,617,,16607,0'
    gps = event(cursor, 'collection_gps_raw', capture, 'gps', raw_line=gps_line, seq=5, fix=0,
        lat=None, lon=None, alt=None, speed=None, sats=0, hdop=99.99, age=617, utc='', chars=16607, errors=0)
    require(one(cursor, 'SELECT raw_line,lat,lon,alt,speed FROM collection_gps_raw WHERE id=%s',
                (gps,)) == (gps_line, None, None, None, None))
    radar = event(cursor, 'collection_radar_raw', capture, 'radar', payload_json='{}', frames=0,
                  bytes=0, age_ms=None, stale=1)
    target = insert(cursor, 'collection_radar_targets', dict(parent_id=radar, slot=1, ordinal=0,
        present=0, x_mm=0, y_mm=0, speed_cms=0, resolution_mm=0))
    require(one(cursor, 'SELECT age_ms FROM collection_radar_raw WHERE id=%s', (radar,))[0] is None)
    counts = {}
    for stream, table in (('insole', 'collection_insole_frames'), ('gps', 'collection_gps_raw'),
                          ('radar', 'collection_radar_raw')):
        counts[stream] = one(cursor, 'SELECT COUNT(*) FROM `' + table + '` WHERE capture_id=%s', (capture,))[0]
    require(counts == dict(insole=1, gps=1, radar=1))
    declared = canonical(counts)
    cursor.execute('UPDATE collection_sessions SET mobile_stopped_at=%s,server_stopped_at=%s,'
        'final_counts_json=%s,finalization_state=%s WHERE capture_id=%s',
        (WHEN, WHEN, declared, 'verified', capture))
    require(one(cursor, 'SELECT final_counts_json,finalization_state FROM collection_sessions '
                'WHERE capture_id=%s', (capture,)) == (declared, 'verified'))
    # An existing child blocks its parent, and an absent parent blocks its child.
    rejected(cursor, 1644 if verify_patient_purge else 1451,
             'DELETE FROM patients WHERE id=%s', (owned['patient'],))
    rejected(cursor, 1452, 'UPDATE collection_gps_raw SET capture_id=%s WHERE id=%s', (str(uuid4()), gps))
    rejected(cursor, 1062, 'INSERT INTO collection_gps_raw SELECT * FROM collection_gps_raw WHERE id=%s', (gps,))
    audit_id = str(uuid4())
    insert(cursor, 'clinical_audit_event', dict(id=audit_id, trace_id=str(uuid4()), actor_id=owned['owner'],
        patient_id=owned['patient'], action='synthetic_verify', result='synthetic', canonical_payload='{}',
        event_hash=digest(audit_id), created_at=WHEN))
    rejected(cursor, 1644, 'UPDATE clinical_audit_event SET result=%s WHERE id=%s', ('changed', audit_id))
    owned['deletes'] = [('clinical_audit_event', 'id', audit_id),
        ('collection_radar_targets', 'id', target), ('collection_radar_raw', 'id', radar),
        ('collection_gps_raw', 'id', gps), ('collection_insole_frames', 'id', insole),
        ('device_transformed_data', 'id', transformed), *[('device_raw_data', 'id', key) for key in raw],
        ('collection_sessions', 'capture_id', capture)]


def scoped_delete_cases(cursor, owned):
    # Every attempted delete is an exact row created by this transaction.
    for table, key, identity in owned['deletes']:
        rejected(cursor, 1644, 'DELETE FROM `' + table + '` WHERE `' + key + '`=%s', (identity,))
    operation = str(uuid4())
    insert(cursor, 'data_management_operation', dict(id=operation, request_id=str(uuid4()), preview_id=str(uuid4()),
        actor_id=owned['owner'], owner_id=owned['owner'], patient_id=owned['patient'], kind='capture',
        record_id=owned['capture'], scope_json='{}', scope_hash=digest(operation), inventory_json='{}',
        counts_json='{}', trace_id=str(uuid4()), stage='planned', state='running', discard_pending=0, created_at=WHEN))
    for table, _, identity in owned['deletes']:
        insert(cursor, 'data_management_item', dict(operation_id=operation, table_name=table, row_id=str(identity)))
    rejected(cursor, 1644, 'DELETE FROM collection_sessions WHERE capture_id=%s', (owned['capture'],))
    cursor.execute('UPDATE data_management_operation SET stage=%s WHERE id=%s', ('agent_purged', operation))
    audit_id = owned['deletes'][0][2]
    rejected(cursor, 1644, 'UPDATE clinical_audit_event SET result=%s WHERE id=%s', ('changed', audit_id))
    # A sibling row outside the fixed item set remains protected even during a valid operation.
    rejected(cursor, 1644, 'DELETE FROM collection_sessions WHERE capture_id=%s', (owned['sibling'],))
    for table, key, identity in owned['deletes']:
        cursor.execute('DELETE FROM `' + table + '` WHERE `' + key + '`=%s', (identity,))
        require(cursor.rowcount == 1)
    require(one(cursor, 'SELECT COUNT(*) FROM collection_sessions WHERE capture_id IN (%s,%s)',
                (owned['sibling'], owned['legacy']))[0] == 2)
    require(one(cursor, 'SELECT COUNT(*) FROM patients WHERE id=%s AND clinician_id=%s',
                (owned['patient'], owned['owner']))[0] == 1)
    insert(cursor, 'data_management_item', dict(operation_id=operation, table_name='collection_sessions',
                                              row_id=owned['sibling']))
    cursor.execute('UPDATE data_management_operation SET state=%s WHERE id=%s', ('complete', operation))
    rejected(cursor, 1644, 'DELETE FROM collection_sessions WHERE capture_id=%s', (owned['sibling'],))


def export_storage_cases(cursor, owned):
    bundle_id = str(uuid4())
    token_hash = digest(str(uuid4()))
    insert(cursor, 'data_export_inventory', dict(
        id=bundle_id, actor_id=owned['owner'], patient_id=owned['patient'],
        request_json='{}', inventory_json='{}', scope_hash=digest(bundle_id),
        state='ready', created_at=WHEN, lease_until=WHEN, expires_at=WHEN,
    ))
    rejected(cursor, 1452, 'INSERT INTO data_export_grant (token_hash,export_id,expires_at) VALUES (%s,%s,%s)',
             (token_hash, str(uuid4()), WHEN))
    insert(cursor, 'data_export_grant', dict(token_hash=token_hash, export_id=bundle_id, expires_at=WHEN))
    require(one(cursor, 'SELECT export_id FROM data_export_grant WHERE token_hash=%s', (token_hash,))[0] == bundle_id)
    cursor.execute('DELETE FROM data_export_inventory WHERE id=%s AND patient_id=%s', (bundle_id, owned['patient']))
    require(cursor.rowcount == 1)
    require(one(cursor, 'SELECT COUNT(*) FROM data_export_grant WHERE token_hash=%s', (token_hash,))[0] == 0)


def patient_purge_cases(cursor, owned):
    patient = dict(clinician_id=owned['owner'], subject_id='p' + uuid4().hex[:19], gender='男')
    patient_id = insert(cursor, 'patients', patient)
    insert(cursor, 'patient_pii', dict(patient_id=patient_id, name='synthetic'))
    targets = (('patient_pii', 'patient_id'), ('patients', 'id'))
    for table, key in targets:
        rejected(cursor, 1644, f'DELETE FROM {table} WHERE {key}=%s', (patient_id,))
    operation = str(uuid4())
    insert(cursor, 'data_management_operation', dict(
        id=operation, request_id=operation, preview_id=operation, actor_id=owned['owner'],
        owner_id=owned['owner'], patient_id=patient_id, kind='patient', record_id=None,
        scope_json='{}', scope_hash=digest(operation), inventory_json='{}', counts_json='{}',
        trace_id=operation, stage='agent_purged', state='running', discard_pending=0, created_at=WHEN,
    ))
    for table, key in targets:
        insert(cursor, 'data_management_item', dict(operation_id=operation, table_name=table, row_id=str(patient_id)))
        cursor.execute(f'DELETE FROM {table} WHERE {key}=%s', (patient_id,))
        require(cursor.rowcount == 1)
    cursor.execute("UPDATE data_management_operation SET stage='completed', state='completed' WHERE id=%s", (operation,))
    rejected(cursor, 1644, 'INSERT INTO patients (id,clinician_id,subject_id,gender) VALUES (%s,%s,%s,%s)',
             (patient_id, patient['clinician_id'], patient['subject_id'], patient['gender']))
    cursor.execute(
        "SELECT column_name FROM information_schema.statistics WHERE table_schema=DATABASE() "
        "AND table_name='data_management_item' AND index_name='ix_management_item_identity' ORDER BY seq_in_index"
    )
    require(tuple(row[0] for row in cursor.fetchall()) == ('table_name', 'row_id'))


def verify(env_file, enabled, *, verify_export=False, verify_patient_purge=False):
    require(enabled)
    phase('configuration')
    import pymysql
    from dotenv import dotenv_values
    require(env_file.is_file())
    values = dotenv_values(env_file, interpolate=False)
    require(all(values.get(key) for key in ('DB_HOST', 'DB_USER', 'DB_PASS')))
    port = int(values.get('DB_PORT') or '3306')
    require(1 <= port <= 65535)
    # Never use DB_NAME, a URL, an ambient env or an application factory.
    connection = pymysql.connect(host=values['DB_HOST'], port=port, user=values['DB_USER'],
        password=values['DB_PASS'], database=DATABASE, charset='utf8mb4', autocommit=False,
        connect_timeout=5, read_timeout=15, write_timeout=15)
    try:
        connection.begin()
        with connection.cursor() as cursor:
            phase('preflight')
            preflight(cursor, verify_export=verify_export)
            phase('registration_null_legacy')
            owned = fixtures(cursor)
            phase('counts_and_constraints')
            storage_cases(cursor, owned, verify_patient_purge=verify_patient_purge)
            phase('scoped_delete_and_protection')
            scoped_delete_cases(cursor, owned)
            if verify_export:
                phase('export_storage')
                export_storage_cases(cursor, owned)
            if verify_patient_purge:
                phase('patient_purge')
                patient_purge_cases(cursor, owned)
    finally:
        # Including every error path: no persistent fixtures and no explicit delete cleanup.
        # MySQL may consume AUTO_INCREMENT ids despite rollback; gaps are expected.
        try:
            connection.rollback()
        finally:
            connection.close()
    print('MYSQL_COLLECTION_REGISTRATION_VERIFY_OK transaction=rolled_back storage_only=true')
    if verify_export:
        print('MYSQL_EXPORT_STORAGE_VERIFY_OK transaction=rolled_back')
    if verify_patient_purge:
        print('MYSQL_PATIENT_PURGE_VERIFY_OK transaction=rolled_back')


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise VerificationFailure('invalid_arguments')


def main(argv=None):
    try:
        parser = SafeParser(description=__doc__, allow_abbrev=False)
        parser.add_argument('--env-file', required=True, type=Path,
                            help='Explicit existing credential file; only DB_HOST/PORT/USER/PASS read')
        parser.add_argument('--allow-isolated-write-rollback', action='store_true', required=True,
                            help='Explicitly enable synthetic writes to the fixed verify schema only')
        parser.add_argument('--verify-export-storage', action='store_true',
                            help='Also verify migration 010 tables and the grant foreign key')
        parser.add_argument('--verify-patient-purge', action='store_true',
                            help='Verify migration 011 scoped deletes and retired identity protections')
        args = parser.parse_args(argv)
        verify(args.env_file, args.allow_isolated_write_rollback, verify_export=args.verify_export_storage,
               verify_patient_purge=args.verify_patient_purge)
        return 0
    except SystemExit as error:
        return 0 if error.code == 0 else 1
    except BaseException:
        # Fixed phase only: no connection strings, DB errors, row ids, payloads or credentials.
        print('MYSQL_COLLECTION_REGISTRATION_VERIFY_FAILED phase=' + _phase)
        return 1


if __name__ == '__main__':
    sys.exit(main())
