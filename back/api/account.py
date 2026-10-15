"""Authenticated role context without changing the App's login DTO."""

from flask import Blueprint, g, jsonify
from utils import Response, token_required

account_bp = Blueprint('account', __name__)


@account_bp.route('/account/context', methods=['GET'])
@token_required()
def account_context():
    account = g.account_context
    return jsonify(Response.success(data={'clinician_id': account.clinician_id, 'role': account.role}))
