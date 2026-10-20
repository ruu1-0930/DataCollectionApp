"""Verifier safety checks only; these do not emulate MySQL business acceptance."""
import importlib.util
from decimal import Decimal
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
import re
from threading import Event
from types import SimpleNamespace

import pytest


@pytest.fixture
def verifier():
    path = Path(__file__).resolve().parents[1] / 'tools/verify_collection_gps_mysql.py'
    assert path.is_file(), 'E03 verifier has not been implemented'
    spec = importlib.util.spec_from_file_location('gps_mysql_verifier', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one(self):
        return self.rows[0][0]

    def all(self):
        return self.rows


class Boundary:
    """Only preflight SQL; accidental writes fail immediately."""
    def __init__(self, database='lanya_gps_verify_20261020', version='8.0.36',
                 engine='InnoDB', nonempty=False, missing=False):
        self.database, self.version, self.engine = database, version, engine
        self.nonempty, self.missing = nonempty, missing
        self.statements = []

    def exec_driver_sql(self, sql, parameters=None):
        self.statements.append(sql)
        assert sql.lstrip().upper().startswith('SELECT'), 'preflight attempted DML'
        if sql == 'SELECT DATABASE()':
            return Rows([(self.database,)])
        if sql == 'SELECT VERSION()':
            return Rows([(self.version,)])
        if 'information_schema.tables' in sql:
            names = ['clinicians', 'patients', 'devices', 'device_raw_data',
                     'collection_sessions', 'collection_insole_frames', 'collection_gps_raw']
            return Rows([(n, self.engine) for n in names[1:] if self.missing] if self.missing
                        else [(n, self.engine) for n in names])
        if 'COUNT(*)' in sql:
            return Rows([(int(self.nonempty),)])
        raise AssertionError('unexpected preflight query')


@pytest.mark.parametrize('change', [dict(database='lanya'), dict(version='5.7.44'),
                                  dict(version='8.0.36-MariaDB'), dict(engine='MyISAM'),
                                  dict(nonempty=True), dict(missing=True)])
def test_preflight_refuses_unsafe_target_before_dml(verifier, change):
    connection = Boundary(**change)
    with pytest.raises(verifier.VerificationFailure):
        verifier.preflight(connection)
    assert all(sql.startswith('SELECT') for sql in connection.statements)


def test_preflight_accepts_only_empty_fixed_mysql8_innodb(verifier):
    verifier.preflight(Boundary())


@pytest.mark.parametrize('change', [dict(clinician_id=99), dict(patient_id=99),
                                  dict(device_id=99), dict(capture_id='foreign')])
def test_cleanup_rejects_foreign_row_before_delete(verifier, change):
    row = dict(clinician_id=1, patient_id=2, device_id=3, capture_id='owned')
    row.update(change)
    with pytest.raises(verifier.VerificationFailure):
        verifier.check_owned_capture(row, dict(clinician_id=1, patient_id=2,
                                              device_id=3, captures={'owned'}))


def test_cleanup_refuses_wrong_schema_without_delete(verifier):
    connection = Boundary(database='lanya')
    with pytest.raises(verifier.VerificationFailure):
        verifier.cleanup(connection, {})
    assert connection.statements == ['SELECT DATABASE()']


def test_cleanup_refuses_live_worker_before_delete(verifier):
    connection = Boundary()
    with pytest.raises(verifier.VerificationFailure):
        verifier.cleanup(connection, {'workers': [SimpleNamespace(is_alive=lambda: True)]})
    assert connection.statements == ['SELECT DATABASE()']


def test_cleanup_refuses_changed_synthetic_owner_before_delete(verifier):
    class ForeignOwner(Boundary):
        def execute(self, statement):
            assert statement.is_select, 'cleanup attempted delete before checking owner'
            return SimpleNamespace(mappings=lambda: SimpleNamespace(
                first=lambda: {'hospital': 'someone-else'}))
    with pytest.raises(verifier.VerificationFailure):
        verifier.cleanup(ForeignOwner(), dict(clinician_id=1, patient_id=2, device_id=3,
            marker='own-run', subject='own-subject', captures=['own-capture']))


def test_wait_timeout_is_bounded_and_does_not_open_gate(verifier):
    gate = Event()
    with pytest.raises(verifier.VerificationFailure):
        verifier.wait_for(gate, timeout=0.001)
    assert not gate.is_set()


def test_safe_failure_output_omits_exception_payload_and_success_marker(verifier):
    output = StringIO()
    def failed():
        raise RuntimeError('mysql+pymysql://user:password@host/lanya GPS1,private')
    assert verifier.run_safely(failed, output) == 1
    assert re.fullmatch(r'FAIL verification \[checkpoint=startup, category=unexpected, '
                        r'helper_line=\d+\] \(details suppressed\)\n', output.getvalue())


def test_cli_has_no_database_or_url_override(verifier):
    for option in ('--database', '--url'):
        with pytest.raises(SystemExit) as rejected:
            verifier.arguments([option, 'lanya'])
        assert rejected.value.code != 0


def double_results():
    """Use real model/driver dialect processors offline, without a DB or service fake."""
    from sqlalchemy.dialects.mysql.pymysql import dialect
    from models.models import CollectionGpsRaw
    mysql = dialect()
    original = dict(lat=31.230123456789, lon=121.470987654321,
                    alt=12.3456789, speed=1.23456789, hdop=1.123456789)
    processed = {}
    for name, value in original.items():
        implementation = CollectionGpsRaw.__table__.c[name].type.dialect_impl(mysql)
        processor = implementation.result_processor(mysql, None)
        processed[name] = processor(value) if processor else value
    return original, processed, mysql


def test_real_mysql_model_processor_does_not_make_valid_double_storage_fail(verifier):
    original, processed, mysql = double_results()
    assert processed['lat'] == Decimal('31.2301234568')
    assert processed['lat'] != 31.230123456789  # old helper comparison is false
    verifier.check_double_values(processed, original, mysql)


def test_double_storage_check_does_not_tolerate_driver_precision_loss(verifier):
    original, processed, mysql = double_results()
    original['lat'] = 31.2301234568  # same 10-place view, genuinely different raw double
    with pytest.raises(verifier.VerificationFailure):
        verifier.check_double_values(processed, original, mysql)


def test_diagnostic_uses_allowlist_checkpoint_category_and_local_line_only(verifier):
    verifier.checkpoint('gps.double_storage')
    secret = 'mysql+pymysql://user:password@host GPS1,private'
    error_class = type(secret, (RuntimeError,), {})
    try:
        verifier.require(False)
    except verifier.VerificationFailure as error:
        detail = verifier.failure_detail(error)
    assert 'checkpoint=gps.double_storage' in detail
    assert 'category=condition' in detail
    assert 'helper_line=' in detail
    assert 'category=unexpected' in verifier.failure_detail(error_class(secret))
    assert secret not in detail
    with pytest.raises(verifier.VerificationFailure):
        verifier.checkpoint(secret)


class ClockMetadata:
    """Only the external metadata/session reads; no business or DB result simulation."""
    def __init__(self, mode='', columns=None):
        self.mode = mode
        self.columns = columns if columns is not None else [
            ('collected_at', 'datetime', 3), ('uploaded_at', 'datetime', 0)]

    def exec_driver_sql(self, sql):
        if 'information_schema.columns' in sql:
            return Rows(self.columns)
        assert sql == 'SELECT @@SESSION.sql_mode'
        return Rows([(self.mode,)])


@pytest.mark.parametrize('server,collected,uploaded,mode', [
    ('2026-10-20 23:59:58.499', '2026-10-21 07:59:58.499', '2026-10-21 07:59:58', ''),
    ('2026-10-20 23:59:58.500', '2026-10-21 07:59:58.500', '2026-10-21 07:59:59', ''),
    ('2026-10-20 23:59:58.501', '2026-10-21 07:59:58.501', '2026-10-21 07:59:59', ''),
    ('2026-10-20 15:59:59.999', '2026-10-20 23:59:59.999', '2026-10-21 00:00:00', ''),
    ('2026-10-20 23:59:58.500', '2026-10-21 07:59:58.500', '2026-10-21 07:59:58',
     'STRICT_TRANS_TABLES,TIME_TRUNCATE_FRACTIONAL'),
    ('2026-10-20 15:59:59.999', '2026-10-20 23:59:59.999', '2026-10-20 23:59:59',
     'TIME_TRUNCATE_FRACTIONAL'),
])
def test_raw_clock_checks_same_server_instant_at_declared_precision(
        verifier, server, collected, uploaded, mode):
    frame = dict(server_received_at=datetime.fromisoformat(server),
                 mobile_received_at=datetime(2026, 10, 19))
    row = dict(collected_at=datetime.fromisoformat(collected), uploaded_at=datetime.fromisoformat(uploaded))
    verifier.check_raw_clock(frame, [row, dict(row)], ClockMetadata(mode))


@pytest.mark.parametrize('fault', ['wrong_second', 'wrong_offset', 'changed_collected',
                                  'mobile_alias', 'lr_mismatch'])
def test_raw_clock_rejects_real_clock_corruption(verifier, fault):
    frame = dict(server_received_at=datetime(2026, 10, 20, 15, 59, 59, 500000),
                 mobile_received_at=datetime(2026, 10, 19))
    row = dict(collected_at=datetime(2026, 10, 20, 23, 59, 59, 500000),
               uploaded_at=datetime(2026, 10, 21))
    rows = [row, dict(row)]
    if fault == 'wrong_second':
        row['uploaded_at'] += timedelta(seconds=1)
    elif fault == 'wrong_offset':
        row['collected_at'] -= timedelta(hours=8)
        row['uploaded_at'] -= timedelta(hours=8)
    elif fault == 'changed_collected':
        row['collected_at'] += timedelta(milliseconds=1)
    elif fault == 'mobile_alias':
        row['collected_at'] = row['uploaded_at'] = frame['mobile_received_at']
    else:
        rows[1]['uploaded_at'] -= timedelta(seconds=1)
    with pytest.raises(verifier.VerificationFailure):
        verifier.check_raw_clock(frame, rows, ClockMetadata())


@pytest.mark.parametrize('columns', [
    [('collected_at', 'datetime', 0), ('uploaded_at', 'datetime', 0)],
    [('collected_at', 'datetime', 3), ('uploaded_at', 'timestamp', 0)],
    [('collected_at', 'datetime', 3), ('uploaded_at', 'datetime', None)],
])
def test_raw_clock_refuses_unexpected_column_metadata(verifier, columns):
    frame = dict(server_received_at=datetime(2026, 10, 20), mobile_received_at=datetime(2026, 10, 19))
    rows = [dict(collected_at=datetime(2026, 10, 20, 8), uploaded_at=datetime(2026, 10, 20, 8))] * 2
    with pytest.raises(verifier.VerificationFailure):
        verifier.check_raw_clock(frame, rows, ClockMetadata(columns=columns))


def driver_error(code):
    """Real PyMySQL packet decoding and SQLAlchemy wrapping, with no connection."""
    import struct
    import pymysql
    from sqlalchemy.exc import DBAPIError
    packet = b'\xff' + struct.pack('<H', code) + b'#HY000' + b'synthetic private SQL/URI/GPS1'
    try:
        pymysql.err.raise_mysql_exception(packet)
    except pymysql.err.Error as original:
        return DBAPIError.instance('private SQL', {'payload': 'private GPS1'}, original, pymysql.err.Error)
    raise AssertionError('real driver did not reject error packet')


@pytest.mark.parametrize('code,kind', [(1062, 'IntegrityError'), (1452, 'IntegrityError'),
                                      (3819, 'OperationalError')])
def test_expected_constraint_rejection_accepts_actual_driver_classification(verifier, code, kind):
    error = driver_error(code)
    assert type(error.orig).__name__ == kind
    def rejected():
        raise error
    verifier.expect_db_rejection(code, rejected)


@pytest.mark.parametrize('code', [1142, 1062])
def test_constraint_check_propagates_unexpected_exact_errno(verifier, code):
    error = driver_error(code)
    def rejected():
        raise error
    with pytest.raises(type(error)) as caught:
        verifier.expect_db_rejection(3819, rejected)
    assert caught.value is error


def test_constraint_check_propagates_missing_errno(verifier):
    import pymysql
    from sqlalchemy.exc import DBAPIError
    error = DBAPIError.instance('private SQL', {}, pymysql.err.OperationalError(), pymysql.err.Error)
    def rejected():
        raise error
    with pytest.raises(DBAPIError) as caught:
        verifier.expect_db_rejection(3819, rejected)
    assert caught.value is error


def test_constraint_check_refuses_operation_success(verifier):
    with pytest.raises(verifier.VerificationFailure):
        verifier.expect_db_rejection(3819, lambda: None)


@pytest.mark.parametrize('unsafe_code', [True, '3819', 10**30])
def test_safe_errno_never_formats_noninteger_or_unbounded_values(verifier, unsafe_code):
    import pymysql
    from sqlalchemy.exc import DBAPIError
    error = DBAPIError.instance('private SQL', {}, pymysql.err.OperationalError(unsafe_code, 'private'),
                              pymysql.err.Error)
    assert verifier.mysql_errno(error) is None
    assert 'mysql_errno=' not in verifier.failure_detail(error)


def test_safe_diagnostic_reports_only_actual_integer_errno(verifier):
    output = StringIO()
    error = driver_error(3819)
    def rejected():
        raise error
    assert verifier.run_safely(rejected, output) == 1
    assert re.fullmatch(r'FAIL verification \[checkpoint=startup, category=database, '
                        r'helper_line=\d+, mysql_errno=3819\] \(details suppressed\)\n', output.getvalue())
