"""Offline helper safety only; no MySQL acceptance or connection is performed."""
import importlib.util
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_verifier():
    path = Path(__file__).resolve().parents[1] / 'tools/verify_collection_radar_mysql.py'
    assert path.is_file(), 'radar operator helper is not implemented'
    spec = importlib.util.spec_from_file_location('radar_mysql_verifier',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Rows:
    def __init__(self,rows):
        self.rows = rows
    def scalar_one(self):
        return self.rows[0][0]
    def all(self):
        return self.rows


class SelectBoundary:
    """Accept only bounded preflight SELECTs; accidental DML fails immediately."""
    def __init__(self,database='lanya_radar_verify_20261023',version='8.0.36',engine='InnoDB',nonempty=False,missing=False,extra=False):
        self.database,self.version,self.engine = database,version,engine
        self.nonempty,self.missing,self.extra = nonempty,missing,extra
        self.statements = []
    def exec_driver_sql(self,sql):
        self.statements.append(sql)
        assert sql.startswith('SELECT'), 'preflight must never perform DML'
        if sql == 'SELECT DATABASE()':
            return Rows([(self.database,)])
        if sql == 'SELECT VERSION()':
            return Rows([(self.version,)])
        if 'information_schema.tables' in sql:
            names = ['clinicians','patients','devices','device_raw_data','collection_sessions',
                     'collection_insole_frames','collection_gps_raw','collection_radar_raw','collection_radar_targets']
            if self.missing:
                names.pop()
            if self.extra:
                names.append('unrelated_business')
            return Rows([(name,self.engine) for name in names])
        if sql.startswith('SELECT COUNT(*) FROM'):
            return Rows([(int(self.nonempty),)])
        raise AssertionError('unexpected query')


@pytest.mark.parametrize('over',[dict(database='lanya'),dict(version='5.7.44'),dict(version='8.0.15'),
    dict(version='8.0.36-MariaDB'),dict(engine='MyISAM'),dict(nonempty=True),dict(missing=True),dict(extra=True)])
def test_unsafe_preflight_refused_before_dml(over):
    verifier = load_verifier()
    connection = SelectBoundary(**over)
    with pytest.raises(verifier.VerificationFailure):
        verifier.preflight(connection)
    assert all(sql.startswith('SELECT') for sql in connection.statements)


@pytest.mark.parametrize('version',['8.0.16','8.0.36','8.4.3'])
def test_fixed_empty_mysql_with_enforced_checks_is_accepted(version):
    verifier = load_verifier()
    verifier.preflight(SelectBoundary(version=version))


def test_cleanup_refuses_foreign_identity_before_first_delete():
    verifier = load_verifier()
    class ForeignOwner(SelectBoundary):
        def execute(self,statement):
            assert statement.is_select, 'must check ownership before DELETE'
            return SimpleNamespace(mappings=lambda:SimpleNamespace(first=lambda:dict(hospital='foreign')))
    owned = dict(marker='radar-verify-own',subject='rv-own',clinician_id=1,patient_id=2,device_id=3,capture_id='own')
    with pytest.raises(verifier.VerificationFailure):
        verifier.cleanup(ForeignOwner(),owned)
    wrong_schema = SelectBoundary(database='lanya')
    with pytest.raises(verifier.VerificationFailure):
        verifier.cleanup(wrong_schema,owned)
    assert wrong_schema.statements == ['SELECT DATABASE()']


def test_target_credentials_cannot_select_production_database(tmp_path):
    verifier = load_verifier()
    env = tmp_path/'synthetic.env'
    env.write_text('DB_HOST=synthetic.invalid\nDB_USER=synthetic\nDB_PASS=private\nDB_NAME=lanya\n',encoding='utf-8')
    url = verifier.target_url(env)
    assert url.database == 'lanya_radar_verify_20261023'
    assert url.host == 'synthetic.invalid'


def test_failure_diagnostic_and_cli_never_echo_sensitive_input():
    verifier = load_verifier()
    sensitive = 'mysql+pymysql://user:password@private/lanya GPS1,private'
    output = StringIO()
    def fail():
        raise RuntimeError(sensitive)
    assert verifier.run_safely(fail,output) == 1
    assert sensitive not in output.getvalue()
    assert 'category=unexpected' in output.getvalue()
    assert 'MYSQL_RADAR_VERIFY_OK' not in output.getvalue()
    output = StringIO()
    assert verifier.main(['--url',sensitive],output) == 1
    assert 'private' not in output.getvalue() and 'password' not in output.getvalue()


@pytest.mark.parametrize('expected,actual',[(1062,1062),(1452,1452),(3819,3819),(3819,1142),(3819,None)])
def test_constraint_requires_exact_actual_mysql_errno(expected,actual):
    verifier = load_verifier()
    import pymysql
    from sqlalchemy.exc import DBAPIError
    args = () if actual is None else (actual,'private injected diagnostic')
    error = DBAPIError.instance('private SQL',{},pymysql.err.OperationalError(*args),pymysql.err.Error)
    def fail():
        raise error
    if actual == expected:
        verifier.expect_rejection(expected,fail)
    else:
        with pytest.raises(DBAPIError) as caught:
            verifier.expect_rejection(expected,fail)
        assert caught.value is error
    output = StringIO()
    assert verifier.run_safely(fail,output) == 1
    assert 'private' not in output.getvalue()
    assert 'MYSQL_RADAR_VERIFY_OK' not in output.getvalue()


def test_constraint_success_is_not_accepted_as_rejection():
    verifier = load_verifier()
    with pytest.raises(verifier.VerificationFailure):
        verifier.expect_rejection(3819,lambda:None)
