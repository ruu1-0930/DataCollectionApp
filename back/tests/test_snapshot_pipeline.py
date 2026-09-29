"""Behavioral tests for the pre-publication deterministic snapshot build."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import threading
import time
from types import SimpleNamespace

import pytest

from services.snapshot_contracts import SnapshotUnavailableError
from services.snapshot_pipeline import AnalyzerFunctions, SnapshotPipeline


T0 = datetime(2026, 9, 29, 10, 0, 0)


def revision():
    return SimpleNamespace(
        id="00000000-0000-4000-8000-000000000001",
        patient_id=7,
        device_id=13,
        session_key="P7-20260929T100000000000",
        state="closed_by_inactivity",
        first_row_id=1,
        last_row_id=4,
        row_count=4,
        last_accepted_row_id=4,
        ordered_row_ids_canonical="[1,2,3,4]",
        event_start_at=T0,
        event_end_at=T0 + timedelta(seconds=1),
        ingest_start_at=T0,
        ingest_end_at=T0 + timedelta(seconds=1),
        closure_policy_version="gap-v1",
        closure_evidence_canonical=(
            '{"policy_version":"gap-v1","observed_at":"2026-09-29T10:00:31.000000",'
            '"last_accepted_at":"2026-09-29T10:00:01.000000","idle_seconds":"30",'
            '"reason":"device_quiet_period","next_accepted_row_id":null}'
        ),
        closed_at=T0 + timedelta(seconds=31),
    )


def raw_row(row_id, foot, collected_at, **overrides):
    row = {
        "id": row_id,
        "patient_id": 7,
        "device_id": 13,
        "foot": foot,
        "collected_at": collected_at,
        "uploaded_at": collected_at,
        "step_length": 0.6,
        "walking_speed": 1.2,
        "single_support_time": 0.4,
        "double_support_time": 0.2,
        "ax": 1.0,
        "ay": 2.0,
        "az": 3.0,
        "gx": 4.0,
        "gy": 5.0,
        "gz": 6.0,
    }
    row.update({f"p{index}": float(index * 10) for index in range(1, 10)})
    row.update(overrides)
    return row


def rows():
    return [
        raw_row(1, "L", T0),
        raw_row(2, "R", T0),
        raw_row(3, "L", T0 + timedelta(seconds=1)),
        raw_row(4, "R", T0 + timedelta(seconds=1)),
    ]


def test_build_from_revision_loads_once_filters_before_analyzers_and_preserves_input():
    source = rows() + [raw_row(5, "X", T0 + timedelta(seconds=1))]
    original = deepcopy(source)
    fetches = []
    observed = []
    source_revision = revision()
    source_revision.last_row_id = 5
    source_revision.last_accepted_row_id = 5
    source_revision.row_count = 5
    source_revision.ordered_row_ids_canonical = "[1,2,3,4,5]"

    def load_once(value):
        fetches.append(value.id)
        return source

    defaults = AnalyzerFunctions.defaults()

    def metric(rows, frames):
        observed.append(rows)
        assert all(row["foot"] in {"L", "R"} for row in rows)
        assert all(type(row).__name__ == "mappingproxy" for row in rows)
        return defaults.metrics(rows, frames)

    product = SnapshotPipeline(
        row_loader=load_once,
        analyzers=AnalyzerFunctions(
            metrics=metric,
            quality=defaults.quality,
            pressure=defaults.pressure,
            chart=defaults.chart,
        ),
    ).build_from_revision(source_revision)

    assert fetches == [source_revision.id]
    assert len(observed) == 1
    assert source == original
    assert product.full_snapshot["session"]["row_count"] == 5
    assert product.full_snapshot["exclusions"] == [
        {"reason_code": "invalid_foot", "count": 1}
    ]


def test_independent_analyzers_overlap_but_evidence_waits_for_their_results():
    metric_started = threading.Event()
    quality_started = threading.Event()
    observed = []
    defaults = AnalyzerFunctions.defaults()

    def metric(filtered_rows, frames):
        metric_started.set()
        assert quality_started.wait(timeout=1)
        observed.append("metrics")
        return defaults.metrics(filtered_rows, frames)

    def quality(filtered_rows, frames):
        quality_started.set()
        assert metric_started.wait(timeout=1)
        observed.append("quality")
        return defaults.quality(filtered_rows, frames)

    pipeline = SnapshotPipeline(
        analyzers=AnalyzerFunctions(
            metrics=metric,
            quality=quality,
            pressure=defaults.pressure,
            chart=defaults.chart,
        )
    )

    product = pipeline.build(revision=revision(), filtered_rows=rows())

    assert observed == ["metrics", "quality"] or observed == ["quality", "metrics"]
    statuses = {status.name: status.state for status in product.analyzer_statuses}
    assert statuses["evidence_index"] == "success"


def test_build_assembly_and_independent_hashes_do_not_depend_on_completion_order():
    defaults = AnalyzerFunctions.defaults()

    def delayed(delay, function):
        def wrapped(filtered_rows, frames):
            time.sleep(delay)
            return function(filtered_rows, frames)
        return wrapped

    fast_metrics = AnalyzerFunctions(
        metrics=delayed(0.00, defaults.metrics),
        quality=delayed(0.03, defaults.quality),
        pressure=delayed(0.02, defaults.pressure),
        chart=delayed(0.01, defaults.chart),
    )
    slow_metrics = AnalyzerFunctions(
        metrics=delayed(0.03, defaults.metrics),
        quality=delayed(0.00, defaults.quality),
        pressure=delayed(0.01, defaults.pressure),
        chart=delayed(0.02, defaults.chart),
    )

    first = SnapshotPipeline(analyzers=fast_metrics).build(
        revision=revision(), filtered_rows=rows()
    )
    second = SnapshotPipeline(analyzers=slow_metrics).build(
        revision=revision(), filtered_rows=rows()
    )

    assert first.full_snapshot == second.full_snapshot
    assert first.agent_projection == second.agent_projection
    assert first.full_snapshot["content_hash"] != first.agent_projection[
        "projection_content_hash"
    ]
    assert "chart_series" not in first.agent_projection
    assert "ordered_row_ids" not in first.full_snapshot["session"]


@pytest.mark.parametrize("required", ["metrics", "quality"])
def test_required_analyzer_failure_makes_the_prepublication_snapshot_unavailable(required):
    defaults = AnalyzerFunctions.defaults()

    def fail(*_args):
        raise RuntimeError("synthetic required analyzer failure")

    analyzers = AnalyzerFunctions(
        metrics=fail if required == "metrics" else defaults.metrics,
        quality=fail if required == "quality" else defaults.quality,
        pressure=defaults.pressure,
        chart=defaults.chart,
    )

    with pytest.raises(SnapshotUnavailableError, match=required + "_failed"):
        SnapshotPipeline(analyzers=analyzers).build(
            revision=revision(), filtered_rows=rows()
        )


def test_optional_chart_failure_is_recorded_without_corrupting_projection():
    defaults = AnalyzerFunctions.defaults()

    def fail_chart(*_args):
        raise RuntimeError("synthetic optional chart failure")

    product = SnapshotPipeline(
        analyzers=AnalyzerFunctions(
            metrics=defaults.metrics,
            quality=defaults.quality,
            pressure=defaults.pressure,
            chart=fail_chart,
        )
    ).build(revision=revision(), filtered_rows=rows())

    statuses = {status.name: status.state for status in product.analyzer_statuses}
    assert statuses["chart"] == "failed"
    assert product.full_snapshot["analyzer_statuses"]["chart"] == "failed"
    assert product.full_snapshot["analyzer_status_reasons"]["chart"] == "chart_failed"
    assert product.full_snapshot["chart_series"] == []
    assert "chart_unavailable" in product.agent_projection["limitations"]
    assert product.agent_projection["metrics"][0]["metric_id"] == "walking_speed_mps"


def test_limited_quality_is_a_valid_withheld_snapshot_not_an_analyzer_failure():
    limited_rows = [raw_row(1, "L", T0)]
    limited_revision = revision()
    limited_revision.last_row_id = 1
    limited_revision.last_accepted_row_id = 1
    limited_revision.row_count = 1
    limited_revision.ordered_row_ids_canonical = "[1]"
    limited_revision.event_end_at = T0
    limited_revision.ingest_end_at = T0

    product = SnapshotPipeline().build(revision=limited_revision, filtered_rows=limited_rows)

    statuses = {status.name: status.state for status in product.analyzer_statuses}
    assert statuses["metrics"] == "success"
    assert statuses["quality"] == "success"
    assert product.agent_projection["data_quality"]["status"] == "limited"
    assert product.agent_projection["data_quality"]["gate"] == "withheld"
    assert product.agent_projection["analyzer_statuses"]["data_quality"] == "success"
    assert all(flag["status"] == "unknown" for flag in product.agent_projection["flags"])
    assert all(flag["reason_codes"] == ["data_quality_withheld"]
               for flag in product.agent_projection["flags"])
    assert product.agent_projection["pressure_summary"]["attention"]["quality"] == "insufficient"
    assert product.agent_projection["pressure_summary"]["attention"]["level"] is None


def test_nonfinite_raw_values_have_distinct_prefilter_fingerprints_and_are_excluded_from_dtos():
    nan_rows = rows()
    infinity_rows = rows()
    nan_rows[0]["walking_speed"] = float("nan")
    infinity_rows[0]["walking_speed"] = float("inf")

    nan_product = SnapshotPipeline().build(revision=revision(), filtered_rows=nan_rows)
    infinity_product = SnapshotPipeline().build(revision=revision(), filtered_rows=infinity_rows)

    assert nan_product.full_snapshot["session"]["raw_data_fingerprint"] != (
        infinity_product.full_snapshot["session"]["raw_data_fingerprint"]
    )
    assert nan_product.full_snapshot["exclusions"] == [
        {"reason_code": "non_finite_numeric", "count": 1}
    ]
    assert "NaN" not in repr(nan_product.full_snapshot)
    assert "Infinity" not in repr(infinity_product.agent_projection)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda source: source.pop(),
        lambda source: source.append(raw_row(5, "L", T0 + timedelta(seconds=2))),
        lambda source: source.__setitem__(2, deepcopy(source[1])),
        lambda source: source.__setitem__(slice(0, 2), [source[1], source[0]]),
    ],
    ids=["missing", "extra", "duplicate", "out_of_order"],
)
@pytest.mark.parametrize("entrypoint", ["direct", "injected_loader"])
def test_every_build_entrypoint_rejects_any_frozen_manifest_mismatch(mutate, entrypoint):
    source = rows()
    mutate(source)

    with pytest.raises(SnapshotUnavailableError, match="revision_row_manifest_mismatch"):
        if entrypoint == "direct":
            SnapshotPipeline().build(revision=revision(), filtered_rows=source)
        else:
            SnapshotPipeline(row_loader=lambda _revision: source).build_from_revision(revision())


def test_frozen_manifest_rejects_event_bounds_that_disagree_with_source_rows():
    invalid_revision = revision()
    invalid_revision.event_end_at = T0 + timedelta(seconds=2)

    with pytest.raises(SnapshotUnavailableError, match="revision_bounds_mismatch"):
        SnapshotPipeline().build(revision=invalid_revision, filtered_rows=rows())


def test_legacy_utc_plus_eight_naive_times_convert_at_dto_boundary_without_changing_raw_hash():
    source = rows()
    legacy_revision = revision()
    legacy_revision.event_start_at = datetime(2026, 9, 29, 0, 30, 0)
    legacy_revision.event_end_at = datetime(2026, 9, 29, 0, 30, 1)
    legacy_revision.ingest_start_at = legacy_revision.event_start_at
    legacy_revision.ingest_end_at = legacy_revision.event_end_at
    legacy_revision.closed_at = datetime(2026, 9, 29, 0, 31, 0)
    legacy_revision.closure_evidence_canonical = (
        '{"policy_version":"gap-v1","observed_at":"2026-09-29T00:31:00.000000",'
        '"last_accepted_at":"2026-09-29T00:30:01.000000","idle_seconds":"30",'
        '"reason":"device_quiet_period","next_accepted_row_id":null}'
    )
    source[0]["collected_at"] = legacy_revision.event_start_at
    source[0]["uploaded_at"] = legacy_revision.event_start_at
    source[1]["collected_at"] = legacy_revision.event_start_at
    source[1]["uploaded_at"] = legacy_revision.event_start_at
    source[2]["collected_at"] = legacy_revision.event_end_at
    source[2]["uploaded_at"] = legacy_revision.event_end_at
    source[3]["collected_at"] = legacy_revision.event_end_at
    source[3]["uploaded_at"] = legacy_revision.event_end_at

    product = SnapshotPipeline().build(revision=legacy_revision, filtered_rows=source)

    assert product.full_snapshot["session"]["start_at"] == "2026-09-28T16:30:00.000Z"
    assert product.full_snapshot["session"]["end_at"] == "2026-09-28T16:30:01.000Z"
    assert product.full_snapshot["session"]["closure"]["closed_at"] == "2026-09-28T16:31:00.000Z"
    assert product.full_snapshot["session"]["closure"]["evidence_at"] == "2026-09-28T16:31:00.000Z"
    from services.gait_session_revision import raw_rows_fingerprint
    assert product.full_snapshot["session"]["raw_data_fingerprint"] == raw_rows_fingerprint(
        patient_id=7, device_id=13, session_id=legacy_revision.session_key, rows=source
    )
    repeated = SnapshotPipeline().build(revision=legacy_revision, filtered_rows=source)
    assert product.full_snapshot == repeated.full_snapshot
    assert product.agent_projection == repeated.agent_projection


def test_optional_pressure_failure_is_statused_without_corrupting_projection():
    defaults = AnalyzerFunctions.defaults()

    def fail_pressure(*_args):
        raise RuntimeError("synthetic optional pressure failure")

    product = SnapshotPipeline(analyzers=AnalyzerFunctions(
        metrics=defaults.metrics, quality=defaults.quality, pressure=fail_pressure,
        chart=defaults.chart,
    )).build(revision=revision(), filtered_rows=rows())

    assert product.agent_projection["analyzer_statuses"]["pressure"] == "failed"
    assert product.agent_projection["analyzer_status_reasons"]["pressure"] == "pressure_failed"
    assert product.agent_projection["pressure_summary"] is None


def test_evidence_index_failure_makes_the_build_unavailable():
    defaults = AnalyzerFunctions.defaults()

    def fail_evidence(*_args):
        raise RuntimeError("synthetic evidence failure")

    with pytest.raises(SnapshotUnavailableError, match="evidence_index_failed"):
        SnapshotPipeline(analyzers=AnalyzerFunctions(
            metrics=defaults.metrics, quality=defaults.quality, pressure=defaults.pressure,
            chart=defaults.chart, evidence_index=fail_evidence,
        )).build(revision=revision(), filtered_rows=rows())


@pytest.mark.parametrize("field,value,reason", [
    ("row_count", 3, "revision_row_manifest_mismatch"),
    ("first_row_id", 2, "revision_row_manifest_mismatch"),
    ("last_row_id", 3, "revision_row_manifest_mismatch"),
    ("last_accepted_row_id", 3, "revision_bounds_mismatch"),
    ("ingest_start_at", T0 - timedelta(seconds=1), "revision_bounds_mismatch"),
    ("ingest_end_at", T0 + timedelta(seconds=2), "revision_bounds_mismatch"),
    ("ordered_row_ids_canonical", "[1,2,2,4]", "revision_row_manifest_mismatch"),
    ("ordered_row_ids_canonical", "[true,2,3,4]", "revision_row_manifest_mismatch"),
])
def test_frozen_manifest_metadata_is_checked_before_hash_or_filter(monkeypatch, field, value, reason):
    invalid_revision = revision()
    setattr(invalid_revision, field, value)
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid frozen input reached hash/filter")
    monkeypatch.setattr("services.snapshot_pipeline.raw_rows_fingerprint", forbidden)
    monkeypatch.setattr(SnapshotPipeline, "_filter_rows", forbidden)
    with pytest.raises(SnapshotUnavailableError, match=reason):
        SnapshotPipeline(row_loader=lambda _revision: rows()).build_from_revision(invalid_revision)


@pytest.mark.parametrize("scope_field", ["patient_id", "device_id"])
@pytest.mark.parametrize("entrypoint", ["direct", "injected_loader"])
def test_every_build_entrypoint_rejects_scope_mismatch(scope_field, entrypoint):
    source = rows()
    source[0][scope_field] += 1
    with pytest.raises(SnapshotUnavailableError, match="revision_scope_mismatch"):
        if entrypoint == "direct":
            SnapshotPipeline().build(revision=revision(), filtered_rows=source)
        else:
            SnapshotPipeline(row_loader=lambda _revision: source).build_from_revision(revision())


@pytest.mark.parametrize("offset", [0, 8, -5])
def test_aware_timestamps_are_normalized_without_legacy_reinterpretation(offset):
    aware_revision = revision()
    source = rows()
    zone = timezone(timedelta(hours=offset))
    for field in ("event_start_at", "event_end_at", "ingest_start_at", "ingest_end_at", "closed_at"):
        setattr(aware_revision, field, getattr(aware_revision, field).replace(tzinfo=zone))
    import json
    closure = json.loads(aware_revision.closure_evidence_canonical)
    closure["observed_at"] = aware_revision.closed_at.isoformat()
    aware_revision.closure_evidence_canonical = json.dumps(closure)
    for row in source:
        for field in ("collected_at", "uploaded_at"):
            row[field] = row[field].replace(tzinfo=zone)
    product = SnapshotPipeline().build(revision=aware_revision, filtered_rows=source)
    session = product.full_snapshot["session"]
    for actual, source_time in (
        (session["start_at"], aware_revision.event_start_at),
        (session["end_at"], aware_revision.event_end_at),
        (session["closure"]["closed_at"], aware_revision.closed_at),
        (session["closure"]["evidence_at"], aware_revision.closed_at),
    ):
        assert actual == source_time.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    repeated = SnapshotPipeline().build(revision=aware_revision, filtered_rows=source)
    assert product.full_snapshot == repeated.full_snapshot
    assert product.agent_projection == repeated.agent_projection


@pytest.mark.parametrize("speed,double_support,attention_metric", [
    (0.2, 0.2, "walking_speed_mps"),
    (1.2, 4.0, "double_support_ratio_pct"),
])
def test_withheld_single_side_preserves_metrics_but_suppresses_attention_and_normal_flags(
    speed, double_support, attention_metric,
):
    from services.gait_analysis import aggregate_session, build_session_flags, build_snapshot_frames
    source = [raw_row(1, "L", T0, walking_speed=speed, double_support_time=double_support)]
    limited = revision()
    limited.last_row_id = limited.last_accepted_row_id = limited.row_count = 1
    limited.ordered_row_ids_canonical = "[1]"
    limited.event_end_at = limited.ingest_end_at = T0
    original = aggregate_session(build_snapshot_frames(source))["metrics"]
    original_flags = build_session_flags(original)
    assert next(flag for flag in original_flags if flag["metric_key"] == attention_metric)["status"] == "attention"
    assert any(flag["status"] == "normal" for flag in original_flags)
    product = SnapshotPipeline().build(revision=limited, filtered_rows=source)
    for payload in (product.full_snapshot, product.agent_projection):
        assert payload["data_quality"]["gate"] == "withheld"
        assert all(flag["status"] == "unknown" for flag in payload["flags"])
        assert all(flag["reason_codes"] == ["data_quality_withheld"] for flag in payload["flags"])
        assert next(metric for metric in payload["metrics"] if metric["metric_id"] == attention_metric)["value_decimal"] is not None
        assert all(metric["reason_codes"] for metric in payload["metrics"] if metric["value_decimal"] is None)


@pytest.mark.parametrize("node", ["pressure", "chart"])
def test_optional_empty_nodes_have_explicit_persisted_state_and_reason(node):
    defaults = AnalyzerFunctions.defaults()
    functions = dict(metrics=defaults.metrics, quality=defaults.quality,
                     pressure=defaults.pressure, chart=defaults.chart)
    functions[node] = lambda *_args: None if node == "pressure" else []
    product = SnapshotPipeline(analyzers=AnalyzerFunctions(**functions)).build(
        revision=revision(), filtered_rows=rows()
    )
    for payload in (product.full_snapshot, product.agent_projection):
        assert payload["analyzer_statuses"][node] == "empty"
        assert payload["analyzer_status_reasons"][node] == (
            "no_pressure_samples" if node == "pressure" else "no_chart_points"
        )
        assert node + "_unavailable" in payload["limitations"]
        assert payload["analyzer_statuses"]["evidence_index"] == "success"


def test_zero_valid_pressure_samples_are_empty_but_keep_counts():
    source = rows()
    for row in source:
        row.update({f"p{index}": 0.0 for index in range(1, 10)})
    product = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    assert product.agent_projection["analyzer_statuses"]["pressure"] == "empty"
    assert product.agent_projection["analyzer_status_reasons"]["pressure"] == "no_pressure_samples"
    assert product.agent_projection["pressure_summary"]["left"]["sensors"]["p1"]["total_samples"] == 2


def test_withheld_quality_suppresses_pressure_attention_even_with_bilateral_pressure_evidence():
    source = []
    for second in range(4):
        for foot in (("L", "R") if second < 3 else ("L",)):
            source.append(raw_row(
                len(source) + 1, foot, T0 + timedelta(seconds=second),
                **{f"p{index}": 100.0 if foot == "L" else 10.0 for index in range(1, 10)},
            ))
    limited = revision()
    limited.last_row_id = limited.last_accepted_row_id = limited.row_count = 7
    limited.ordered_row_ids_canonical = "[1,2,3,4,5,6,7]"
    limited.event_end_at = limited.ingest_end_at = T0 + timedelta(seconds=3)
    defaults = AnalyzerFunctions.defaults()
    assert defaults.pressure(source, ())["attention"]["level"] is not None
    product = SnapshotPipeline().build(revision=limited, filtered_rows=source)
    for payload in (product.full_snapshot, product.agent_projection):
        assert payload["data_quality"]["gate"] == "withheld"
        assert payload["pressure_summary"]["matched_sensor_count"] == 9
        assert payload["pressure_summary"]["attention"] == {
            "level": None, "quality": "insufficient", "reason_codes": ["data_quality_withheld"],
        }
    assert next(status for status in product.analyzer_statuses if status.name == "evidence_index").required


def test_empty_required_evidence_index_cannot_be_a_successful_snapshot():
    defaults = AnalyzerFunctions.defaults()
    with pytest.raises(SnapshotUnavailableError, match="evidence_index_empty"):
        SnapshotPipeline(analyzers=AnalyzerFunctions(
            metrics=defaults.metrics, quality=defaults.quality, pressure=defaults.pressure,
            chart=defaults.chart, evidence_index=lambda *_args: [],
        )).build(revision=revision(), filtered_rows=rows())
