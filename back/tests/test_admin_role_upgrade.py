"""Final role model and forward-only enum steps; not an executed MySQL rehearsal."""

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


def test_admin_is_a_valid_final_role_but_old_readonly_value_is_not(db):
    from models.models import Clinician
    assert Clinician.__table__.c.role.type.enums == ['clinician', 'admin']
    db.session.execute(text("INSERT INTO clinicians (hospital,dept,name,phone,passcode_hash,role) "
                            "VALUES ('synthetic','synthetic','synthetic','13800000001','synthetic','admin')"))
    db.session.commit()
    assert db.session.query(Clinician).one().role == 'admin'
    with pytest.raises(IntegrityError):
        db.session.execute(text("UPDATE clinicians SET role='admin_readonly'"))
        db.session.commit()
    db.session.rollback()


def test_role_upgrade_assets_keep_expansion_and_contraction_separate():
    root = Path(__file__).resolve().parents[1]
    files = [root / 'migrations' / name for name in ('004a_admin_role_expand.sql', '004b_admin_role_contract.sql')]
    assert all(path.is_file() for path in files), 'Forward role migration steps are missing'
    statements = ['\n'.join(line for line in path.read_text(encoding='utf-8').splitlines()
                            if not line.strip().startswith('--')).strip() for path in files]
    assert all(sql.count(';') == 1 and sql.startswith('ALTER TABLE') for sql in statements)
    assert "ENUM('clinician','admin_readonly','admin')" in statements[0]
    assert "ENUM('clinician','admin')" in statements[1]
    assert all("DEFAULT 'clinician'" in sql and 'UPDATE ' not in sql for sql in statements)
