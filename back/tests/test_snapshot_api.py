"""Strict HTTP boundary for the B snapshot service."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
from uuid import uuid4

import pytest

from auth import issue_token
from config import db
from models.models import AnalysisSnapshot, Clinician, Device, DeviceRawData, Patient
from services.analysis_snapshot import AnalysisSnapshotService
from services.gait_session_revision import _session_id, parse_session_start
from services.snapshot_contracts import _validator


NOW = datetime(2026, 9, 28, 16, 31, tzinfo=timezone.utc)
START = datetime(2026, 9, 29, 0, 30)


@pytest.fixture
def scope(app):
    app.config["SNAPSHOT_SERVICE_FACTORY"] = lambda: AnalysisSnapshotService(clock=lambda: NOW)
    owner = Clinician(hospital="synthetic", dept="D", name="owner-secret", phone="1", passcode_hash="x")
    other = Clinician(hospital="synthetic", dept="D", name="other", phone="2", passcode_hash="x")
    db.session.add_all([owner, other])
    db.session.flush()
    patient = Patient(clinician_id=owner.id, subject_id="secret-patient")
    device = Device(clinician_id=owner.id, device_code="snapshot-api-device")
    db.session.add_all([patient, device])
    db.session.flush()
    for second in range(4):
        for foot in ("L", "R"):
            at = START + timedelta(seconds=second)
            db.session.add(DeviceRawData(
                clinician_id=owner.id, patient_id=patient.id, device_id=device.id,
                foot=foot, collected_at=at, uploaded_at=at,
                **{f"p{i}": 10.0 for i in range(1, 10)},
                ax=1, ay=2, az=3, gx=4, gy=5, gz=6, step_length=.6,
                walking_speed=1.2, single_support_time=.4, double_support_time=.2,
            ))
    db.session.commit()
    tokens = {"owner": issue_token(owner.id), "other": issue_token(other.id)}
    result = dict(patient_id=patient.id, actor_id=owner.id, other_id=other.id,
                  session_id=_session_id(patient.id, START), tokens=tokens)
    db.session.remove()
    return result


def auth(scope, who="owner"):
    return {"Authorization": "Bearer " + scope["tokens"][who]}


def ensure_url(scope, patient_id=None):
    patient_id = scope["patient_id"] if patient_id is None else patient_id
    return f"/patients/{patient_id}/gait/sessions/{scope['session_id']}/snapshots:ensure"


def snapshot_url(scope, snapshot_id, tail="", patient_id=None):
    patient_id = scope["patient_id"] if patient_id is None else patient_id
    return f"/patients/{patient_id}/gait/snapshots/{snapshot_id}{tail}"


def created(client, scope):
    response = client.post(ensure_url(scope), headers=auth(scope))
    assert response.status_code == 201, response.json
    return response.json["snapshot_id"]


def error(response, code, status):
    assert response.status_code == status, response.json
    _validator("ErrorEnvelopeV1").validate(response.json)
    assert response.json["error"]["code"] == code
    text = response.get_data(as_text=True)
    for secret in ("owner-secret", "secret-patient", "snapshot-api-device", "p1=123"):
        assert secret not in text


def test_ensure_create_reuse_and_strict_success_contracts(client, scope):
    snapshot_id = created(client, scope)
    reused = client.post(ensure_url(scope), headers=auth(scope), json={})
    assert reused.status_code == 200 and reused.json["snapshot_id"] == snapshot_id
    _validator("AnalysisSnapshotV1").validate(reused.json)
    full = client.get(snapshot_url(scope, snapshot_id), headers=auth(scope))
    projection = client.get(snapshot_url(scope, snapshot_id, "/agent-projection"), headers=auth(scope))
    status = client.get(snapshot_url(scope, snapshot_id, "/status"), headers=auth(scope))
    for response, schema in ((full, "AnalysisSnapshotV1"),
                             (projection, "AgentSnapshotProjectionV1"),
                             (status, "SnapshotStatusV1")):
        assert response.status_code == 200, response.json
        _validator(schema).validate(response.json)
        assert "owner-secret" not in response.get_data(as_text=True)
        assert "secret-patient" not in response.get_data(as_text=True)
    assert status.json == {"snapshot_id": snapshot_id, "state": "published",
                           "snapshot_state_version": 1, "content_hash": full.json["content_hash"],
                           "superseded_by": None}
    assert "metrics" not in status.json and "patient_id" not in status.json
    assert "chart_series" not in projection.json


def test_claim_create_reuse_conflict_and_stale(client, scope):
    snapshot_id = created(client, scope)
    body = {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64}
    url = snapshot_url(scope, snapshot_id, "/publication-claims")
    first = client.post(url, headers=auth(scope), json=body)
    again = client.post(url, headers=auth(scope), json=body)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json == again.json and first.json["actor_id"] == scope["actor_id"]
    _validator("SnapshotPublicationClaimV1").validate(first.json)
    error(client.post(url, headers=auth(scope), json={**body, "candidate_hash": "b" * 64}), "claim_conflict", 409)
    error(client.post(url, headers=auth(scope), json={**body, "snapshot_state_version": 2}), "stale_snapshot", 409)


@pytest.mark.parametrize("surface", ["ensure", "full", "status", "projection", "claim"])
def test_authentication_and_ownership_precede_reads(client, scope, surface, monkeypatch):
    snapshot_id = created(client, scope)
    paths = {"ensure": ensure_url(scope), "full": snapshot_url(scope, snapshot_id),
             "status": snapshot_url(scope, snapshot_id, "/status"),
             "projection": snapshot_url(scope, snapshot_id, "/agent-projection"),
             "claim": snapshot_url(scope, snapshot_id, "/publication-claims")}
    path = paths[surface]
    method = client.post if surface in {"ensure", "claim"} else client.get
    kwargs = {"json": {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()),
                        "candidate_hash": "a" * 64}} if surface == "claim" else {}
    error(method(path, **kwargs), "unauthorized", 401)
    error(method(path, headers={"Authorization": "Bearer invalid"}, **kwargs), "unauthorized", 401)
    # A foreign clinician must not reach the exact snapshot lookup.
    from services.snapshot_repository import AnalysisSnapshotRepository
    monkeypatch.setattr(AnalysisSnapshotRepository, "snapshot", lambda *_: pytest.fail("snapshot lookup before ownership"))
    error(method(path, headers=auth(scope, "other"), **kwargs), "forbidden", 403)
    error(method(path.replace(f"/patients/{scope['patient_id']}/", "/patients/999999/"),
                 headers=auth(scope), **kwargs), "patient_not_found", 404)


def test_revoked_clinician_token_and_existing_gait_envelope(client, scope):
    db.session.delete(db.session.get(Clinician, scope["other_id"]))
    db.session.commit()
    error(client.get(snapshot_url(scope, str(uuid4())), headers=auth(scope, "other")), "unauthorized", 401)
    legacy = client.get(f"/patients/{scope['patient_id']}/gait/sessions", headers=auth(scope))
    assert legacy.status_code == 200 and set(legacy.json) == {"code", "msg", "data"}


@pytest.mark.parametrize("route", ["full", "status", "projection", "claim"])
def test_missing_snapshot_404(client, scope, route):
    missing = str(uuid4())
    tail = {"full": "", "status": "/status", "projection": "/agent-projection",
            "claim": "/publication-claims"}[route]
    body = {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64}
    method = client.post if route == "claim" else client.get
    kwargs = {"json": body} if route == "claim" else {}
    error(method(snapshot_url(scope, missing, tail), headers=auth(scope), **kwargs), "snapshot_not_found", 404)


def test_ensure_missing_invalid_and_collecting(client, scope):
    valid = scope["session_id"]
    scope["session_id"] = _session_id(scope["patient_id"], START - timedelta(days=1))
    error(client.post(ensure_url(scope), headers=auth(scope)), "session_not_found", 404)
    scope["session_id"] = "not-a-session"
    error(client.post(ensure_url(scope), headers=auth(scope)), "invalid_request", 400)
    scope["session_id"] = valid
    db.session.add(DeviceRawData(
        clinician_id=scope["actor_id"], patient_id=scope["patient_id"], device_id=Device.query.one().id,
        foot="L", collected_at=START + timedelta(seconds=4), uploaded_at=START + timedelta(seconds=60),
        **{f"p{i}": 10.0 for i in range(1, 10)}, ax=1, ay=2, az=3, gx=4, gy=5, gz=6,
        step_length=.6, walking_speed=1.2, single_support_time=.4, double_support_time=.2,
    ))
    db.session.commit()
    error(client.post(ensure_url(scope), headers=auth(scope)), "collection_in_progress", 409)


def test_late_data_supersedes_full_projection_claim_but_status_stays_metadata(client, scope):
    snapshot_id = created(client, scope)
    row = DeviceRawData.query.first()
    db.session.add(DeviceRawData(
        clinician_id=row.clinician_id, patient_id=row.patient_id, device_id=row.device_id,
        foot="L", collected_at=START, uploaded_at=START,
        **{f"p{i}": 10.0 for i in range(1, 10)}, ax=1, ay=2, az=3, gx=4, gy=5, gz=6,
        step_length=.6, walking_speed=1.2, single_support_time=.4, double_support_time=.2,
    ))
    db.session.commit()
    status = client.get(snapshot_url(scope, snapshot_id, "/status"), headers=auth(scope))
    assert status.status_code == 200 and status.json["state"] == "superseded"
    assert status.json["snapshot_state_version"] == 2
    assert status.json["superseded_by"] is None
    for tail in ("", "/agent-projection"):
        error(client.get(snapshot_url(scope, snapshot_id, tail), headers=auth(scope)), "snapshot_superseded", 409)
    claim = {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64}
    error(client.post(snapshot_url(scope, snapshot_id, "/publication-claims"), headers=auth(scope), json=claim),
          "stale_snapshot", 409)
    historic = client.get(snapshot_url(scope, snapshot_id) + "?include_superseded=true", headers=auth(scope))
    assert historic.status_code == 200 and historic.json["state"] == "superseded"
    _validator("AnalysisSnapshotV1").validate(historic.json)


@pytest.mark.parametrize("bad", [
    {"actor_id": 1}, {"patient_id": 1}, {"unknown": 0}, [], 1,
])
def test_ensure_rejects_nonempty_or_nonobject_body(client, scope, bad):
    error(client.post(ensure_url(scope), headers=auth(scope), json=bad), "invalid_request", 400)


def test_ensure_rejects_explicit_json_null_but_allows_absent_body(client, scope):
    error(client.post(ensure_url(scope), headers=auth(scope), data="null", content_type="application/json"),
          "invalid_request", 400)
    assert client.post(ensure_url(scope), headers=auth(scope)).status_code == 201


@pytest.mark.parametrize("bad", [
    {"snapshot_state_version": True, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64},
    {"snapshot_state_version": 0, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64},
    {"snapshot_state_version": 1.0, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64},
    {"snapshot_state_version": 1, "workflow_run_id": "bad", "candidate_hash": "a" * 64},
    {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "A" * 64},
    {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64, "actor_id": 1},
    [], None, 42,
])
def test_claim_strict_body(client, scope, bad):
    error(client.post(snapshot_url(scope, str(uuid4()), "/publication-claims"),
                      headers=auth(scope), json=bad), "invalid_request", 400)


@pytest.mark.parametrize("path_type", ["full", "status", "projection", "claim"])
def test_invalid_snapshot_uuid_rejected(client, scope, path_type):
    tail = {"full": "", "status": "/status", "projection": "/agent-projection",
            "claim": "/publication-claims"}[path_type]
    method = client.post if path_type == "claim" else client.get
    body = {"snapshot_state_version": 1, "workflow_run_id": str(uuid4()), "candidate_hash": "a" * 64}
    kwargs = {"json": body} if path_type == "claim" else {}
    error(method(snapshot_url(scope, "INVALID-UUID", tail), headers=auth(scope), **kwargs), "invalid_request", 400)


def test_malformed_json_query_keys_and_no_internal_exception_text(client, scope, monkeypatch):
    path = ensure_url(scope)
    error(client.post(path, headers=auth(scope), data="{", content_type="application/json"), "invalid_request", 400)
    error(client.post(path, headers=auth(scope), data='{"x":1,"x":2}', content_type="application/json"),
          "invalid_request", 400)
    error(client.post(path + "?unused=1", headers=auth(scope)), "invalid_request", 400)
    snapshot_id = created(client, scope)
    full = snapshot_url(scope, snapshot_id)
    for query in ("?include_superseded=false", "?include_superseded=true&include_superseded=true",
                  "?unknown=true"):
        error(client.get(full + query, headers=auth(scope)), "invalid_request", 400)
    from api import snapshot as snapshot_api
    def broken():
        raise RuntimeError("owner-secret p1=123")
    monkeypatch.setattr(snapshot_api, "_service", broken)
    error(client.get(full, headers=auth(scope)), "publication_failed", 500)


class ReadSpy(BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.requested = []

    def read(self, size=-1):
        self.requested.append(size)
        return super().read(size)


@pytest.mark.parametrize("route", ["ensure", "claim"])
def test_oversize_known_length_rejected_before_stream_read(client, scope, route):
    path = ensure_url(scope) if route == "ensure" else snapshot_url(scope, str(uuid4()), "/publication-claims")
    body = b"{" + b"x" * 100_000 + b"}"
    stream = ReadSpy(body)
    response = client.open(path, method="POST", headers=auth(scope), content_type="application/json",
                           environ_overrides={"wsgi.input": stream, "CONTENT_LENGTH": str(len(body))})
    error(response, "invalid_request", 400)
    assert stream.requested == []


@pytest.mark.parametrize("route", ["ensure", "claim"])
def test_oversize_unknown_length_reads_at_most_limit_plus_one(client, scope, route):
    path = ensure_url(scope) if route == "ensure" else snapshot_url(scope, str(uuid4()), "/publication-claims")
    stream = ReadSpy(b"{" + b"x" * 100_000 + b"}")
    response = client.open(path, method="POST", headers=auth(scope), content_type="application/json",
                           environ_overrides={"wsgi.input": stream, "wsgi.input_terminated": True,
                                              "CONTENT_LENGTH": ""})
    error(response, "invalid_request", 400)
    assert stream.requested and all(0 <= size <= 2049 for size in stream.requested)
    assert stream.tell() <= 2049


@pytest.mark.parametrize("route", ["ensure", "full", "status", "projection", "claim"])
def test_wrong_method_on_known_snapshot_path_has_strict_error(client, scope, route):
    snapshot_id = str(uuid4())
    path = {"ensure": ensure_url(scope), "full": snapshot_url(scope, snapshot_id),
            "status": snapshot_url(scope, snapshot_id, "/status"),
            "projection": snapshot_url(scope, snapshot_id, "/agent-projection"),
            "claim": snapshot_url(scope, snapshot_id, "/publication-claims")}[route]
    method = client.get if route in {"ensure", "claim"} else client.post
    error(method(path), "invalid_request", 400)


def test_wrong_method_on_legacy_and_unknown_paths_keeps_flask_behavior(client, scope):
    legacy = client.post(f"/patients/{scope['patient_id']}/gait/sessions")
    unknown = client.get("/not-a-snapshot-route")
    assert legacy.status_code == 405 and legacy.json is None
    assert unknown.status_code == 404 and unknown.json is None


@pytest.mark.parametrize("code,status", [
    ("session_superseded", 409), ("snapshot_building", 409), ("scope_mismatch", 409),
    ("snapshot_unavailable", 422), ("internal_invariant_failed", 500),
])
def test_domain_error_mapping_is_allowlisted_and_safe(client, scope, code, status, app):
    from services.snapshot_repository import SnapshotError
    class FailingService:
        def ensure_snapshot(self, **_kwargs):
            raise SnapshotError(code, details={"secret": "owner-secret", "attempt_id": str(uuid4()),
                                               "retry_after_ms": 250})
    app.config["SNAPSHOT_SERVICE_FACTORY"] = FailingService
    response = client.post(ensure_url(scope), headers=auth(scope))
    error(response, code, status)
    assert set(response.json["error"]["details"]) <= {"attempt_id", "retry_after_ms"}


def test_parse_session_start_nonstring_is_safe():
    for value in (None, 1, True, [], {}):
        assert parse_session_start(1, value) is None
