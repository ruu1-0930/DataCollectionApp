"""Management controls remain authorized and available after clinical fencing."""
from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError
from access import AccessError
from api.collection import _body
from services.collection_ingest import CollectionError
from services.data_management import preview_delete, get_delete_preview, begin_delete, get_operation, continue_delete
from utils import token_required

data_management_bp = Blueprint('data_management', __name__)
BASE = '/v2/data-management'


def _respond(call):
    try:
        return jsonify(call())
    except AccessError as error:
        return jsonify(error={'code': error.code}), error.status_code
    except CollectionError as error:
        return jsonify(error={'code': 'invalid_request'}), error.status
    except SQLAlchemyError:
        return jsonify(error={'code': 'management_unavailable'}), 503


@data_management_bp.post(BASE + '/delete-previews')
@token_required('data.manage')
def preview():
    return _respond(lambda: preview_delete(g.account_context, _body(), request.headers['Authorization'].split()[1]))


@data_management_bp.get(BASE + '/delete-previews/<string:preview_id>')
@token_required('data.manage')
def read_preview(preview_id):
    if request.args or request.content_length:
        return jsonify(error={'code': 'invalid_request'}), 400
    return _respond(lambda: get_delete_preview(g.account_context, preview_id))


@data_management_bp.post(BASE + '/operations')
@token_required('data.manage')
def begin():
    return _respond(lambda: begin_delete(g.account_context, _body(), request.headers['Authorization'].split()[1]))


@data_management_bp.get(BASE + '/operations/<string:operation_id>')
@token_required('data.manage')
def operation(operation_id):
    if request.args or request.content_length:
        return jsonify(error={'code': 'invalid_request'}), 400
    return _respond(lambda: get_operation(g.account_context, operation_id))


@data_management_bp.post(BASE + '/operations/<string:operation_id>/continue')
@token_required('data.manage')
def advance(operation_id):
    def run():
        if _body() != {}:
            raise AccessError(400, 'invalid_request')
        return continue_delete(g.account_context, operation_id, request.headers['Authorization'].split()[1])
    return _respond(run)
