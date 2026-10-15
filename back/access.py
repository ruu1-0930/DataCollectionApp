"""Database-backed application capabilities; a JWT role is never authoritative."""

from dataclasses import dataclass
from typing import Literal

from config import db
from models.models import Clinician


@dataclass(frozen=True)
class AccountContext:
    clinician_id: int
    role: Literal['clinician', 'admin_readonly']


class AccessError(RuntimeError):
    def __init__(self, status_code, code):
        self.status_code, self.code = status_code, code
        super().__init__(code)


def load_account_context(clinician_id: int) -> AccountContext:
    if type(clinician_id) is not int or clinician_id < 1:
        raise AccessError(401, 'unauthorized')
    actor = db.session.query(Clinician).populate_existing().filter_by(id=clinician_id).first()
    if actor is None:
        raise AccessError(401, 'unauthorized')
    if actor.role not in {'clinician', 'admin_readonly'}:
        raise AccessError(403, 'forbidden')
    return AccountContext(actor.id, actor.role)


def require_capability(account: AccountContext, capability: str) -> None:
    roles = {'admin.read': 'admin_readonly', 'clinician.write': 'clinician',
             'snapshot.execute': 'clinician'}
    if capability not in roles or account.role != roles[capability]:
        raise AccessError(403, 'forbidden')
