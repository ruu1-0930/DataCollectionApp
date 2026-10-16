"""One directory contract for clinician and global analysis administrator scopes."""

import re
from time import perf_counter

from flask import Blueprint, g, jsonify, request
from jsonschema.exceptions import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from access import AccessError, require_capability
from services.admin_access_log import log_admin_event, normalized_trace_id
from services.workbench_directory import DirectoryQueryError, WorkbenchDirectoryService
from utils import Response, token_required


workbench_bp = Blueprint('workbench', __name__, url_prefix='/workbench')


@workbench_bp.before_request
def authenticate():
    g.directory_trace_id = normalized_trace_id(request.headers.get('X-Trace-ID'))
    g.directory_started_at = perf_counter()
    return token_required('clinical.read')(lambda: None)()


@workbench_bp.after_request
def access_log(response):
    response.headers['X-Trace-ID'] = g.directory_trace_id
    account = getattr(g, 'account_context', None)
    log_admin_event(action=request.endpoint, result=response.status_code, trace_id=g.directory_trace_id,
        actor_id=account.clinician_id if account else None, role=account.role if account else None,
        resource_type='directory', row_count=getattr(g, 'directory_row_count', 0),
        elapsed_ms=int((perf_counter() - g.directory_started_at) * 1000))
    return response


def _options(*, doctors):
    args = request.args
    allowed = {'hospital', 'q', 'page', 'page_size'} | (set() if doctors else {'clinician_id'})
    if set(args) - allowed or any(len(args.getlist(key)) != 1 for key in args):
        raise DirectoryQueryError('invalid_directory_query')
    result = dict(args)
    for key, default in (('page', '1'), ('page_size', '50')):
        result.setdefault(key, default)
    for key in ('page', 'page_size', 'clinician_id'):
        if key in result:
            if not re.fullmatch(r'[1-9][0-9]{0,9}', result[key]):
                raise DirectoryQueryError('invalid_directory_query')
            result[key] = int(result[key])
    return result


def _read(*, doctors):
    try:
        require_capability(g.account_context, 'admin.read' if doctors else 'clinical.read')
        service = WorkbenchDirectoryService()
        operation = service.clinicians if doctors else service.patients
        data = operation(g.account_context, **_options(doctors=doctors))
        g.directory_row_count = len(data['items'])
        return jsonify(Response.success(data))
    except DirectoryQueryError:
        status = 400
    except AccessError as exc:
        status = exc.status_code
    except (SQLAlchemyError, ValidationError, ValueError, TypeError, LookupError):
        status = 503
    messages = {400: '查询参数无效', 401: '账号身份无效', 403: '无权读取此范围', 503: '目录暂不可读'}
    return jsonify(Response.error(status, messages[status])), status


@workbench_bp.get('/patients')
def patients():
    return _read(doctors=False)


@workbench_bp.get('/clinicians')
def clinicians():
    return _read(doctors=True)
