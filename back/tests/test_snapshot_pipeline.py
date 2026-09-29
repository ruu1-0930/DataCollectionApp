"""Behavioral tests for the pre-publication deterministic snapshot build."""

from copy import deepcopy
from datetime import datetime, timedelta
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
        event_start_at=T0,
        event_end_at=T0 + timedelta(seconds=1),
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
    assert product.full_snapshot["chart_series"] == []
    assert "chart_unavailable" in product.agent_projection["limitations"]
    assert product.agent_projection["metrics"][0]["metric_id"] == "walking_speed_mps"


def test_limited_quality_is_a_valid_withheld_snapshot_not_an_analyzer_failure():
    limited_rows = [raw_row(1, "L", T0)]
    limited_revision = revision()
    limited_revision.last_row_id = 1
    limited_revision.last_accepted_row_id = 1
    limited_revision.row_count = 1
    limited_revision.event_end_at = T0

    product = SnapshotPipeline().build(revision=limited_revision, filtered_rows=limited_rows)

    statuses = {status.name: status.state for status in product.analyzer_statuses}
    assert statuses["metrics"] == "success"
    assert statuses["quality"] == "success"
    assert product.agent_projection["data_quality"]["status"] == "limited"
    assert product.agent_projection["data_quality"]["gate"] == "withheld"
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
