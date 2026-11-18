"""Bounded deterministic HTTP calls; never invoked inside a B database transaction."""
import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from flask import current_app


class AgentManagementError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AgentDataManagementClient:
    def request(self, action, payload, token):
        root = current_app.config.get('AGENT_DATA_MANAGEMENT_URL', '')
        parsed = urlsplit(root)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise AgentManagementError('agent_unavailable')
        if action not in {'inventory', 'purge', 'preview-inventory'} or not token:
            raise AgentManagementError('invalid_request')
        request = Request(root.rstrip('/') + '/api/agent/v2/data-management/' + action,
            data=json.dumps(payload, separators=(',', ':'), allow_nan=False).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            try:
                response = build_opener(_NoRedirect()).open(request, timeout=30)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(4 * 1024 * 1024 + 1)
                if len(raw) > 4 * 1024 * 1024:
                    raise AgentManagementError('agent_unavailable')
                result = json.loads(raw)
                if response.code != 200:
                    raise AgentManagementError('agent_busy' if response.code == 409 else 'agent_unavailable')
            from services.data_management import validate
            validate('AgentPreviewInventoryV1' if action == 'preview-inventory' else 'AgentDataInventoryV1' if action == 'inventory' else 'PurgeReceiptV1', result)
            identity = 'preview_id' if action == 'preview-inventory' else 'operation_id'
            if (result[identity], result['scope_hash']) != (payload[identity], payload['scope_hash']):
                raise AgentManagementError('agent_scope_mismatch')
            return result
        except AgentManagementError:
            raise
        except Exception:
            raise AgentManagementError('agent_unavailable') from None
