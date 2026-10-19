"""Bounded, strict collection HTTP boundary; safe errors never echo raw input."""

import json
from flask import Blueprint, request, jsonify, g
from sqlalchemy.exc import SQLAlchemyError
from access import AccessError
from utils import token_required, Response
from services.collection_ingest import CollectionError, create_capture, ingest_batch, stop_capture
from services.gps_query import session_gps


collection_bp = Blueprint('collection', __name__)
BODY_LIMIT = 128 * 1024


def _unique_object(pairs):
    result = {}
    for key,value in pairs:
        if key in result:
            raise CollectionError()
        result[key] = value
    return result


def _body():
    if request.args or request.mimetype != 'application/json':
        raise CollectionError()
    if request.content_length is not None and request.content_length > BODY_LIMIT:
        raise CollectionError()
    raw = request.stream.read(BODY_LIMIT+1)
    if len(raw) > BODY_LIMIT:
        raise CollectionError()
    try:
        return json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(CollectionError()))
    except (ValueError, UnicodeDecodeError):
        raise CollectionError() from None


def _respond(operation):
    try:
        return jsonify(Response.success(data=operation()))
    except (CollectionError,AccessError) as exc:
        code = exc.status if isinstance(exc,CollectionError) else exc.status_code
        return jsonify(Response.error(code,'采集请求无法处理')), code
    except SQLAlchemyError:
        return jsonify(Response.error(503,'采集服务暂不可用')), 503


@collection_bp.post('/collection-sessions')
@token_required('clinician.write')
def create_collection():
    return _respond(lambda:create_capture(g.clinician_id,_body()))


@collection_bp.post('/collection-sessions/<string:capture_id>/batches')
@token_required('clinician.write')
def batch_collection(capture_id):
    return _respond(lambda:ingest_batch(g.clinician_id,capture_id,_body()))


@collection_bp.post('/collection-sessions/<string:capture_id>/stop')
@token_required('clinician.write')
def stop_collection(capture_id):
    return _respond(lambda:stop_capture(g.clinician_id,capture_id,_body()))


@collection_bp.get('/patients/<int:patient_id>/gait/sessions/<string:session_id>/gps')
@token_required('clinical.read')
def get_session_gps(patient_id,session_id):
    def operation():
        if set(request.args) - {'page','page_size'}:
            raise CollectionError()
        pagination = {}
        for key,default,maximum in (('page',1,2147483647),('page_size',500,500)):
            values = request.args.getlist(key)
            if len(values) > 1:
                raise CollectionError()
            value = values[0] if values else str(default)
            if not value.isascii() or not value.isdecimal() or len(value)>10 or not 1 <= int(value) <= maximum:
                raise CollectionError()
            pagination[key] = int(value)
        return session_gps(g.account_context,patient_id,session_id,**pagination)
    return _respond(operation)
