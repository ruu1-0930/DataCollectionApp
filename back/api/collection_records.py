"""Authenticated patient-scoped collection directory and raw reads."""

from flask import Blueprint, g, request

from api.collection import _respond
from services.collection_ingest import CollectionError
from services.collection_records import (
    FILTER_FIELDS, get_record, get_record_verification, list_record_frames,
    list_record_gps, list_record_radar, list_records,
)
from utils import token_required


collection_records_bp = Blueprint('collection_records', __name__)
BASE = '/v2/patients/<int:patient_id>/collections'
RECORD = BASE + '/<string:record_id>'


def _args(allowed):
    if request.content_length or set(request.args) - allowed:
        raise CollectionError()
    if any(len(values) != 1 for _, values in request.args.lists()):
        raise CollectionError()
    return request.args.to_dict()


def _request_limit(args, default):
    value = args.pop('limit', str(default))
    if not value.isascii() or not value.isdecimal() or len(value) > 3:
        raise CollectionError()
    return int(value)


@collection_records_bp.get(BASE)
@token_required('clinical.read')
def records(patient_id):
    def read():
        args = _args(FILTER_FIELDS | {'cursor', 'limit'})
        cursor = args.pop('cursor', None)
        limit = _request_limit(args, 100)
        return list_records(g.account_context, patient_id, args, cursor, limit)
    return _respond(read)


def _detail(reader, patient_id, record_id):
    def read():
        _args(set())
        return reader(g.account_context, patient_id, record_id)
    return _respond(read)


@collection_records_bp.get(RECORD)
@token_required('clinical.read')
def record(patient_id, record_id):
    return _detail(get_record, patient_id, record_id)


@collection_records_bp.get(RECORD + '/verification')
@token_required('clinical.read')
def verification(patient_id, record_id):
    return _detail(get_record_verification, patient_id, record_id)


def _raw(reader, patient_id, record_id):
    def read():
        args = _args({'cursor', 'limit'})
        limit = _request_limit(args, 500)
        return reader(g.account_context, patient_id, record_id, args.get('cursor'), limit)
    return _respond(read)


@collection_records_bp.get(RECORD + '/frames')
@token_required('clinical.read')
def frames(patient_id, record_id):
    return _raw(list_record_frames, patient_id, record_id)


@collection_records_bp.get(RECORD + '/gps')
@token_required('clinical.read')
def gps(patient_id, record_id):
    return _raw(list_record_gps, patient_id, record_id)


@collection_records_bp.get(RECORD + '/radar')
@token_required('clinical.read')
def radar(patient_id, record_id):
    return _raw(list_record_radar, patient_id, record_id)
