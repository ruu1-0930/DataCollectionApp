"""Bounded data reads and short-lived, opaque download grants."""
from flask import Blueprint, Response, g, request
from sqlalchemy.exc import SQLAlchemyError
from access import AccessError
from api.collection import _body
from services.collection_ingest import CollectionError, exact
from services import data_export as service
from utils import token_required

data_export_bp = Blueprint('data_export', __name__, url_prefix='/v2/data-exports')


def _reply(call):
    try:
        value, status = call(), 200
    except AccessError as exc:
        value, status = {'error': {'code': exc.code}}, exc.status_code
    except CollectionError as exc:
        value, status = {'error': {'code': 'invalid_request'}}, exc.status
    except SQLAlchemyError:
        value, status = {'error': {'code':'export_storage_unavailable'}}, 503
    return Response(service.encoded(value), status=status, mimetype='application/json',
                    headers={'Cache-Control':'no-store'})


@data_export_bp.post('')
@token_required('data.manage')
def create():
    return _reply(lambda: service.create_export_inventory(g.account_context, _body()))


@data_export_bp.get('/<export_id>')
@token_required('data.manage')
def status(export_id):
    def run():
        if request.args or request.content_length:
            raise CollectionError()
        return service.export_status(g.account_context,export_id)
    return _reply(run)


@data_export_bp.post('/<export_id>/validate')
@token_required('data.manage')
def validate(export_id):
    def run():
        exact(_body(), ())
        return service.export_status(g.account_context,export_id,validate=True)
    return _reply(run)


@data_export_bp.post('/<export_id>/finish')
@token_required('data.manage')
def finish(export_id):
    def run():
        data = _body()
        exact(data, ('state',))
        return service.finish_export(g.account_context,export_id,data['state'])
    return _reply(run)


@data_export_bp.post('/<export_id>/pages')
@token_required('data.manage')
def page(export_id):
    def run():
        data = _body()
        exact(data, ('kind','cursor','limit','max_bytes','record_id'))
        if not isinstance(data['kind'],str) or data['record_id'] is not None and not isinstance(data['record_id'],str):
            raise CollectionError()
        return service.read_export_page(g.account_context,export_id,**data)
    return _reply(run)


@data_export_bp.post('/<export_id>/download-grants')
@token_required('data.manage')
def grant(export_id):
    def run():
        exact(_body(), ())
        return service.issue_grant(g.account_context,export_id)
    return _reply(run)


@data_export_bp.post('/<export_id>/redeem')
def redeem(export_id):
    def run():
        data = _body()
        exact(data, ('grant',))
        return service.redeem_grant(export_id,data['grant'])
    return _reply(run)

