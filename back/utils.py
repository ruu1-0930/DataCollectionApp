from functools import wraps
from jwt import ExpiredSignatureError, InvalidTokenError
from flask import request, jsonify, g
from auth import decode_token
from access import AccessError, load_account_context, require_capability


class Response:
    @staticmethod
    def success(data=None, msg="操作成功"):
        return {'code': 200, 'msg': msg, 'data': data}

    @staticmethod
    def error(code, msg="操作失败", data=None):
        return {'code': code, 'msg': msg, 'data': data}


def token_required(capability=None):
    """校验 Bearer token，解析 clinician_id 存入 g.clinician_id。"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            auth_header = request.headers.get('Authorization')
            if auth_header:
                parts = auth_header.split()
                if len(parts) == 2 and parts[0] == 'Bearer':
                    token = parts[1]

            if not token:
                return jsonify(Response.error(401, "Token缺失")), 401

            try:
                payload = decode_token(token)
                clinician_id = payload.get('clinician_id')
                if clinician_id is None:
                    return jsonify(Response.error(401, "Token无效: 缺少医护信息")), 401
                account = load_account_context(clinician_id)
                if capability is not None:
                    require_capability(account, capability)
                g.clinician_id = account.clinician_id
                g.account_context = account
            except AccessError as exc:
                message = '无权执行该操作' if exc.status_code == 403 else '医护不存在'
                return jsonify(Response.error(exc.status_code, message)), exc.status_code
            except ExpiredSignatureError:
                return jsonify(Response.error(401, "Token已过期")), 401
            except InvalidTokenError:
                return jsonify(Response.error(401, "Token无效")), 401

            return f(*args, **kwargs)
        return decorated
    return decorator
