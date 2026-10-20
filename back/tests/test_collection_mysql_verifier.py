"""Verifier safety checks only; these do not emulate MySQL business acceptance."""
import importlib.util
from io import StringIO
from pathlib import Path
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
    assert output.getvalue() == 'FAIL verification (details suppressed)\n'


def test_cli_has_no_database_or_url_override(verifier):
    for option in ('--database', '--url'):
        with pytest.raises(SystemExit) as rejected:
            verifier.arguments([option, 'lanya'])
        assert rejected.value.code != 0
