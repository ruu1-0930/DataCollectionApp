"""Bounded server-to-server purge. B never sends a filesystem path to WB."""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener
from flask import current_app
from services.agent_data_management_client import _NoRedirect


class WorkbenchBundleError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def workbench_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('workbench_url_required')
    return value.rstrip('/')


class WorkbenchBundleClient:
    def purge(self, operation, token):
        try:
            root = workbench_url(current_app.config.get('WORKBENCH_DATA_MANAGEMENT_URL', ''))
            if not token:
                raise ValueError('token_required')
            request = Request(root + '/api/data-bundles/purge', method='POST',
                data=json.dumps(dict(schema_version=1, operation_id=operation['operation_id'])).encode(),
                headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
            try:
                response = build_opener(_NoRedirect()).open(request, timeout=30)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(16385)
                if response.code != 200 or len(raw)>16384:
                    raise WorkbenchBundleError('bundle_purge_unavailable')
                return json.loads(raw)
        except WorkbenchBundleError:
            raise
        except Exception:
            raise WorkbenchBundleError('bundle_purge_unavailable') from None
