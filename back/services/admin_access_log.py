"""Small structured operations log, not a second clinical audit database."""

from datetime import datetime, timezone
import json
import logging
from uuid import UUID, uuid4


_META = {'target_account_id', 'previous_role', 'new_role', 'operator', 'resource_type',
         'resource_id', 'owner_clinician_id', 'row_count', 'elapsed_ms'}


def normalized_trace_id(value=None):
    try:
        if isinstance(value, str) and str(UUID(value)) == value:
            return value
    except ValueError:
        pass
    return str(uuid4())


def log_admin_event(*, action, result, actor_id=None, role=None, trace_id=None, **metadata):
    if set(metadata) - _META:
        raise ValueError('unsupported_admin_log_field')
    event = {'time': datetime.now(timezone.utc).isoformat(),
             'trace_id': normalized_trace_id(trace_id), 'actor_id': actor_id,
             'role': role, 'action': action, 'result': result, **metadata}
    logging.getLogger('sarcogait.admin').warning(json.dumps(event, sort_keys=True, ensure_ascii=True))
