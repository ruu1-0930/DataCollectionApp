"""Exercise model defaults/constraints, not a claim of executed MySQL migration."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_role_defaults_for_existing_shape_insert_and_rejects_unknown_role(db):
    db.session.execute(text("INSERT INTO clinicians (hospital,dept,name,phone,passcode_hash) "
                            "VALUES ('synthetic','synthetic','synthetic','13800000001','synthetic')"))
    db.session.commit()
    columns = {c.name for c in db.Model.metadata.tables['clinicians'].columns}
    assert 'role' in columns, 'Clinician role/default migration is not implemented'
    assert db.session.execute(text('SELECT role FROM clinicians')).scalar_one() == 'clinician'
    with pytest.raises(IntegrityError):
        db.session.execute(text("UPDATE clinicians SET role='unknown'"))
        db.session.commit()
    db.session.rollback()


def test_mysql_create_schema_emits_role_default_and_restricted_enum():
    from sqlalchemy.dialects import mysql
    from sqlalchemy.schema import CreateTable
    from models.models import Clinician
    ddl = str(CreateTable(Clinician.__table__).compile(dialect=mysql.dialect()))
    definition = next(line for line in ddl.splitlines()
                      if line.strip().split(' ', 1)[0].strip('`') == 'role')
    assert "ENUM('clinician','admin_readonly')" in definition
    assert 'NOT NULL' in definition
    assert "DEFAULT 'clinician'" in definition
