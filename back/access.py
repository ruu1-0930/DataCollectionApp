"""Database-backed application capabilities; a JWT role is never authoritative."""

from dataclasses import dataclass
from typing import Literal

from config import db
from models.models import Clinician


@dataclass(frozen=True)
class AccountContext:
    clinician_id: int
    role: Literal['clinician', 'admin']


class AccessError(RuntimeError):
    def __init__(self, status_code, code):
        self.status_code, self.code = status_code, code
        super().__init__(code)


def load_account_context(clinician_id: int, *, session=None) -> AccountContext:
    if type(clinician_id) is not int or clinician_id < 1:
        raise AccessError(401, 'unauthorized')
    active_session = db.session if session is None else session
    actor = active_session.query(Clinician).populate_existing().filter_by(id=clinician_id).first()
    if actor is None:
        raise AccessError(401, 'unauthorized')
    if actor.role not in {'clinician', 'admin'}:
        raise AccessError(403, 'forbidden')
    return AccountContext(actor.id, actor.role)


def require_capability(account: AccountContext, capability: str) -> None:
    roles = {'admin.read': {'admin'}, 'clinician.write': {'clinician'},
             'clinical.read': {'clinician', 'admin'}, 'snapshot.execute': {'clinician', 'admin'}}
    if capability not in roles or account.role not in roles[capability]:
        raise AccessError(403, 'forbidden')


def require_patient_scope(account: AccountContext, *, owner_id: int, capability: str) -> None:
    require_capability(account, capability)
    if type(owner_id) is not int or owner_id < 1:
        raise AccessError(403, 'forbidden')
    if account.role != 'admin' and owner_id != account.clinician_id:
        raise AccessError(403, 'forbidden')
