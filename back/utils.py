from functools import wraps
import jwt
from flask import request, jsonify, g
from auth import decode_token
from models.models import Clinician


class Response:
    @staticmethod
    def success(data=None, msg="操作成功"):
        return {'code': 200, 'msg': msg, 'data': data}

    @staticmethod
    def error(code, msg="操作失败", data=None):
        return {'code': code, 'msg': msg, 'data': data}


def token_required():
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
                if not clinician_id:
                    return jsonify(Response.error(401, "Token无效: 缺少医护信息")), 401
                clinician = Clinician.query.get(clinician_id)
                if not clinician:
                    return jsonify(Response.error(401, "医护不存在")), 401
                g.clinician_id = clinician.id
            except jwt.ExpiredSignatureError:
                return jsonify(Response.error(401, "Token已过期")), 401
            except jwt.InvalidTokenError:
                return jsonify(Response.error(401, "Token无效")), 401

            return f(*args, **kwargs)
        return decorated
    return decorator
