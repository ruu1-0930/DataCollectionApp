"""Strict, ownership-enforced HTTP transport for published gait snapshots."""

from functools import wraps
import json
import re
from uuid import UUID

from flask import Blueprint, current_app, g, jsonify, request
from jwt import InvalidTokenError
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from auth import decode_token
from models.models import Clinician
from services.analysis_snapshot import AnalysisSnapshotService, PublicationClaimRequest
from services.snapshot_contracts import _validator
from services.snapshot_repository import SnapshotError


snapshot_bp = Blueprint("snapshot", __name__)

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_HASH = re.compile(r"[0-9a-f]{64}")
_MAX_BODY_BYTES = 2048
_SNAPSHOT_PATHS = (
    re.compile(r"/patients/[1-9][0-9]*/gait/sessions/[^/]+/snapshots:ensure"),
    re.compile(r"/patients/[1-9][0-9]*/gait/snapshots/[^/]+(?:/status|/agent-projection|/publication-claims)?"),
)
_STATUS = {
    "invalid_request": 400, "unauthorized": 401, "forbidden": 403,
    "patient_not_found": 404, "session_not_found": 404, "snapshot_not_found": 404,
    "collection_in_progress": 409, "session_superseded": 409, "snapshot_building": 409,
    "snapshot_superseded": 409, "stale_snapshot": 409, "claim_conflict": 409,
    "scope_mismatch": 409, "snapshot_unavailable": 422,
    "internal_invariant_failed": 500, "publication_failed": 500,
}
_MESSAGE = {
    "invalid_request": "The snapshot request is invalid.",
    "unauthorized": "Authentication is required.",
    "forbidden": "Access to this patient is forbidden.",
    "patient_not_found": "The patient was not found.",
    "session_not_found": "The session was not found.",
    "snapshot_not_found": "The snapshot was not found.",
    "collection_in_progress": "The session is still collecting data.",
    "session_superseded": "The session changed during analysis.",
    "snapshot_building": "The snapshot is being built.",
    "snapshot_superseded": "The snapshot has been superseded.",
    "stale_snapshot": "The snapshot is no longer current.",
    "claim_conflict": "This workflow already claimed a different candidate.",
    "scope_mismatch": "The session source scope is inconsistent.",
    "snapshot_unavailable": "Snapshot analysis is unavailable.",
    "internal_invariant_failed": "Snapshot storage is unavailable.",
    "publication_failed": "Snapshot storage is unavailable.",
}


def _error(code, *, details=None, trace_id=None):
    # No domain exception text, identifiers, or source data enter this envelope.
    if code not in _STATUS:
        code = "publication_failed"
        details, trace_id = None, None
    safe_details = {}
    if code == "snapshot_building" and isinstance(details, dict):
        attempt_id, retry_after_ms = details.get("attempt_id"), details.get("retry_after_ms")
        if isinstance(attempt_id, str) and _UUID.fullmatch(attempt_id):
            safe_details["attempt_id"] = attempt_id
        if type(retry_after_ms) is int and 0 <= retry_after_ms <= 60_000:
            safe_details["retry_after_ms"] = retry_after_ms
    if not isinstance(trace_id, str) or not _UUID.fullmatch(trace_id):
        trace_id = None
    payload = {"error": {"code": code, "message": _MESSAGE[code], "trace_id": trace_id,
                         "retryable": code in {"snapshot_building", "snapshot_unavailable", "publication_failed"},
                         "details": safe_details}}
    _validator("ErrorEnvelopeV1").validate(payload)
    return jsonify(payload), _STATUS[code]


def _route(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except SnapshotError as exc:
            return _error(exc.code, details=exc.details, trace_id=exc.trace_id)
        except Exception:
            return _error("publication_failed")
    return wrapped


@snapshot_bp.app_errorhandler(405)
def _snapshot_method_error(exc):
    # Flask resolves methods before a blueprint is selected. Limit the global
    # handler to exact new snapshot route shapes; legacy Flask 405s stay intact.
    if any(pattern.fullmatch(request.path) for pattern in _SNAPSHOT_PATHS):
        return _error("invalid_request")
    return exc


@snapshot_bp.before_request
def _authenticate():
    auth = request.headers.get("Authorization", "").split()
    if len(auth) != 2 or auth[0] != "Bearer":
        return _error("unauthorized")
    try:
        payload = decode_token(auth[1])
        clinician_id = payload.get("clinician_id")
        if type(clinician_id) is not int or clinician_id < 1:
            return _error("unauthorized")
        clinician = Clinician.query.get(clinician_id)
        if clinician is None:
            return _error("unauthorized")
        g.clinician_id = clinician.id
    except InvalidTokenError:
        return _error("unauthorized")
    except Exception:
        return _error("publication_failed")


def _service():
    factory = current_app.config.get("SNAPSHOT_SERVICE_FACTORY", AnalysisSnapshotService)
    return factory()


def _patient_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]*", value):
        raise SnapshotError("invalid_request")
    return int(value)


def _snapshot_id(value):
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise SnapshotError("invalid_request")
    return UUID(value)


def _query(*, allow_history=False):
    keys = list(request.args.keys())
    if len(keys) != sum(len(request.args.getlist(key)) for key in keys):
        raise SnapshotError("invalid_request")
    if not keys:
        return False
    if allow_history and keys == ["include_superseded"] and request.args["include_superseded"] == "true":
        return True
    raise SnapshotError("invalid_request")


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate_json_key")
        obj[key] = value
    return obj


def _invalid_constant(_value):
    raise ValueError("non_finite_json")


def _body(*, optional=False):
    # A declared size fails before any read. Missing/chunked lengths still have
    # a hard read cap, so a client cannot make us buffer an arbitrary body.
    if request.content_length is not None and request.content_length > _MAX_BODY_BYTES:
        raise SnapshotError("invalid_request")
    try:
        raw = request.stream.read(_MAX_BODY_BYTES + 1)
    except (BadRequest, RequestEntityTooLarge):
        raise SnapshotError("invalid_request") from None
    if len(raw) > _MAX_BODY_BYTES:
        raise SnapshotError("invalid_request")
    if optional and not raw:
        return {}
    if not request.is_json or not raw:
        raise SnapshotError("invalid_request")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
    except (UnicodeError, ValueError):
        raise SnapshotError("invalid_request") from None
    if not isinstance(body, dict):
        raise SnapshotError("invalid_request")
    return body


@snapshot_bp.route("/patients/<patient_id>/gait/sessions/<session_id>/snapshots:ensure", methods=["POST"])
@_route
def ensure_snapshot(patient_id, session_id):
    _query()
    if _body(optional=True):
        raise SnapshotError("invalid_request")
    result = _service().ensure_snapshot(actor_id=g.clinician_id, patient_id=_patient_id(patient_id),
                                         session_id=session_id)
    return jsonify(result.snapshot), 201 if result.created else 200


@snapshot_bp.route("/patients/<patient_id>/gait/snapshots/<snapshot_id>", methods=["GET"])
@_route
def get_snapshot(patient_id, snapshot_id):
    history = _query(allow_history=True)
    result = _service().get_snapshot(actor_id=g.clinician_id, patient_id=_patient_id(patient_id),
                                     snapshot_id=_snapshot_id(snapshot_id), include_superseded=history)
    return jsonify(result.snapshot)


@snapshot_bp.route("/patients/<patient_id>/gait/snapshots/<snapshot_id>/status", methods=["GET"])
@_route
def get_snapshot_status(patient_id, snapshot_id):
    _query()
    result = _service().get_status(actor_id=g.clinician_id, patient_id=_patient_id(patient_id),
                                   snapshot_id=_snapshot_id(snapshot_id))
    return jsonify(result.status)


@snapshot_bp.route("/patients/<patient_id>/gait/snapshots/<snapshot_id>/agent-projection", methods=["GET"])
@_route
def get_snapshot_projection(patient_id, snapshot_id):
    _query()
    result = _service().get_projection(actor_id=g.clinician_id, patient_id=_patient_id(patient_id),
                                       snapshot_id=_snapshot_id(snapshot_id))
    return jsonify(result.projection)


@snapshot_bp.route("/patients/<patient_id>/gait/snapshots/<snapshot_id>/publication-claims", methods=["POST"])
@_route
def claim_snapshot_publication(patient_id, snapshot_id):
    _query()
    body = _body()
    if set(body) != {"snapshot_state_version", "workflow_run_id", "candidate_hash"}:
        raise SnapshotError("invalid_request")
    version, workflow, candidate = body["snapshot_state_version"], body["workflow_run_id"], body["candidate_hash"]
    if (type(version) is not int or version < 1 or not isinstance(workflow, str)
            or not _UUID.fullmatch(workflow) or not isinstance(candidate, str)
            or not _HASH.fullmatch(candidate)):
        raise SnapshotError("invalid_request")
    result = _service().claim_publication(PublicationClaimRequest(
        actor_id=g.clinician_id, patient_id=_patient_id(patient_id), snapshot_id=_snapshot_id(snapshot_id),
        snapshot_state_version=version, workflow_run_id=UUID(workflow), candidate_hash=candidate,
    ))
    return jsonify(result.claim), 201 if result.created else 200
