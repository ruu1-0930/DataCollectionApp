"""Eight fixed, role-guarded GET routes; no generic SQL/proxy interface."""

from datetime import datetime, timedelta
import re
from time import perf_counter
from uuid import UUID

from flask import Blueprint, g, jsonify, request
from jsonschema.exceptions import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from services.admin_access_log import log_admin_event, normalized_trace_id
from services.admin_business import AdminBusinessService, AdminReadError, validate_result
from services.gait_session_revision import parse_session_start
from utils import Response, token_required


admin_business_bp = Blueprint('admin_business', __name__, url_prefix='/admin')
_PAGES = {'page', 'page_size'}
_FILTERS = {
    'list_clinicians': _PAGES | {'hospital', 'dept', 'clinician_id'},
    'list_patients': _PAGES | {'hospital', 'clinician_id', 'patient_id', 'subject_id'},
    'get_patient': set(),
    'list_devices': _PAGES | {'hospital', 'clinician_id', 'device_code'},
    'list_sessions': _PAGES | {'start', 'end'},
    'list_raw_data': _PAGES | {'start', 'end', 'foot', 'device_id'},
    'list_snapshots': _PAGES | {'session_id', 'include_superseded'},
    'get_snapshot': set(),
}
_DTO = dict(zip(_FILTERS, ('AdminClinicianPage', 'AdminPatientPage', 'AdminPatientDetail',
    'AdminDevicePage', 'AdminSessionPage', 'AdminRawPage', 'AdminSnapshotPage', 'AdminStoredSnapshot')))


def _positive(value):
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value):
        raise AdminReadError(400)
    return int(value)


@admin_business_bp.before_request
def authorize():
    g.admin_trace_id = normalized_trace_id(request.headers.get('X-Trace-ID'))
    g.admin_started_at = perf_counter()
    return token_required('admin.read')(lambda: None)()


@admin_business_bp.after_request
def access_log(response):
    response.headers['X-Trace-ID'] = g.admin_trace_id
    account = getattr(g, 'account_context', None)
    log_admin_event(action='admin.' + (request.endpoint or 'unknown').split('.')[-1],
                    result=response.status_code, trace_id=g.admin_trace_id,
                    actor_id=account.clinician_id if account else None, role=account.role if account else None,
                    resource_type='business', resource_id=getattr(g, 'admin_resource_id', None),
                    owner_clinician_id=getattr(g, 'admin_owner_id', None),
                    row_count=getattr(g, 'admin_row_count', 0),
                    elapsed_ms=int((perf_counter() - g.admin_started_at) * 1000))
    return response


def _options(action, patient_id):
    args = request.args
    if set(args) - _FILTERS[action] or any(len(args.getlist(key)) != 1 or not args[key] for key in args):
        raise AdminReadError(400)
    result = dict(args)
    if 'page' in _FILTERS[action]:
        result['page'] = _positive(args.get('page', '1'))
        result['page_size'] = _positive(args.get('page_size', '100' if action == 'list_raw_data' else '50'))
        if result['page_size'] > (500 if action == 'list_raw_data' else 100):
            raise AdminReadError(400)
    for key in ('patient_id', 'clinician_id', 'device_id'):
        if key in result:
            result[key] = _positive(result[key])
    if 'foot' in result and result['foot'] not in ('L', 'R'):
        raise AdminReadError(400)
    if 'include_superseded' in result:
        if result['include_superseded'] not in ('true', 'false'):
            raise AdminReadError(400)
        result['include_superseded'] = result['include_superseded'] == 'true'
    if 'session_id' in result and parse_session_start(patient_id, result['session_id']) is None:
        raise AdminReadError(400)
    for key in ('start', 'end'):
        if key in result:
            try:
                value = datetime.fromisoformat(result[key])
                if value.tzinfo is not None:
                    raise ValueError('naive_required')
                if key == 'end' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', result[key]):
                    value += timedelta(days=1)
                    result['end_exclusive'] = True
                result[key] = value
            except (ValueError, OverflowError):
                raise AdminReadError(400) from None
    if 'start' in result and 'end' in result and (
            result['end'] <= result['start'] if result.get('end_exclusive') else result['end'] < result['start']):
        raise AdminReadError(400)
    return result


def _read(action, patient_id=None, snapshot_id=None):
    try:
        patient_id = _positive(patient_id) if patient_id is not None else None
        if snapshot_id is not None:
            try:
                if str(UUID(snapshot_id)) != snapshot_id:
                    raise ValueError('noncanonical_uuid')
            except ValueError:
                raise AdminReadError(400) from None
        g.admin_resource_id = snapshot_id or patient_id
        value, g.admin_owner_id = AdminBusinessService().read(
            g.account_context, action, _options(action, patient_id), patient_id=patient_id, snapshot_id=snapshot_id)
        validate_result(_DTO[action], value)
        g.admin_row_count = len(value['items']) if 'items' in value else 1
        return jsonify(Response.success(value))
    except AdminReadError as exc:
        code = exc.status_code
    except (SQLAlchemyError, ValidationError, ValueError, TypeError):
        code = 503
    return jsonify(Response.error(code, {400: '查询参数无效', 404: '业务记录不存在或关联不匹配',
                                        503: '业务记录暂不可读'}[code])), code


for _action, _path in (
    ('list_clinicians', '/clinicians'), ('list_patients', '/patients'), ('get_patient', '/patients/<patient_id>'),
    ('list_devices', '/devices'), ('list_sessions', '/patients/<patient_id>/gait/sessions'),
    ('list_raw_data', '/patients/<patient_id>/raw-data'), ('list_snapshots', '/patients/<patient_id>/gait/snapshots'),
    ('get_snapshot', '/patients/<patient_id>/gait/snapshots/<snapshot_id>')):
    def _view(_selected=_action, **kwargs):
        return _read(_selected, **kwargs)
    admin_business_bp.add_url_rule(_path, endpoint=_action, view_func=_view, methods=['GET'])
