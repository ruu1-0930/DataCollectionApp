import jwt
from functools import wraps
from flask import request, jsonify, g
from config import app
from models.models import User

class Response:
    @staticmethod
    def success(data=None, msg="操作成功"):
        return {
            'code': 200,
            'msg': msg,
            'data': data
        }

    @staticmethod
    def error(code, msg="操作失败", data=None):
        return {
            'code': code,
            'msg': msg,
            'data': data
        }


def token_required(role_required=None):
    """
    装饰器：检查请求头中是否包含合法的 token，并解析用户信息
    - 将 user_id 和 role 存入 g.user_id / g.user_role
    - 如果 role_required 不为空，则校验用户权限
    """
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
                payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
                user_id = payload.get('user_id')

                if not user_id:
                    return jsonify(Response.error(401, "Token无效: 缺少用户信息")), 401

                user = User.query.get(user_id)
                if not user:
                    return jsonify(Response.error(401, "用户不存在")), 401

                g.user_id = user.id
                g.user_role = int(user.role)

                # 检查权限
                if role_required is not None and g.user_role < role_required:
                    return jsonify(Response.error(403, "权限不足")), 403

            except jwt.ExpiredSignatureError:
                return jsonify(Response.error(401, "Token已过期")), 401
            except jwt.InvalidTokenError:
                return jsonify(Response.error(401, "Token无效")), 401

            return f(*args, **kwargs)
        return decorated
    return decorator
