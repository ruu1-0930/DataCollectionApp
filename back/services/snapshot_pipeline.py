"""Deterministic, pre-publication analysis over one frozen revision."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
import json
import math
from types import MappingProxyType
from typing import Any

from services.canonical_json import canonical_json_bytes, sha256_hex
from services.gait_analysis import (
    CANONICAL_METRIC_KEYS,
    FIRMWARE_METRICS,
    aggregate_session,
    build_session_flags,
    build_snapshot_frames,
    session_data_quality,
    snapshot_frame_value,
)
from services.gait_session_revision import raw_rows_fingerprint
from services.pressure_analysis import summarize_snapshot_pressure_rows
from services.snapshot_contracts import (
    AnalyzerStatus,
    SnapshotBuildProduct,
    SnapshotUnavailableError,
    validate_build_product,
)


_NUMERIC_COLUMNS = tuple(
    [f"p{index}" for index in range(1, 10)]
    + [
        "ax", "ay", "az", "gx", "gy", "gz", "step_length", "walking_speed",
        "single_support_time", "double_support_time",
    ]
)
_SOURCE_COLUMNS = (
    "id", "patient_id", "device_id", "foot", "collected_at", "uploaded_at", *_NUMERIC_COLUMNS
)
_ANALYZER_ORDER = ("metrics", "quality", "pressure", "chart", "evidence_index")


def _decimal6(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        decimal = Decimal.from_float(value) if isinstance(value, float) else Decimal(value)
        if not decimal.is_finite():
            return None
        rounded = decimal.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        return None
    if rounded == 0:
        rounded = abs(rounded)
    return format(rounded, "f")


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _finite(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (float, Decimal)):
        return value.is_finite() if isinstance(value, Decimal) else math.isfinite(value)
    return value is None or isinstance(value, int)


def _as_mapping(row: Mapping[str, object] | object) -> dict[str, object]:
    if isinstance(row, Mapping):
        return dict(row)
    return {column: getattr(row, column) for column in _SOURCE_COLUMNS}


def _metric_dto(metrics: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    result = []
    for metric_id in CANONICAL_METRIC_KEYS:
        metric = metrics[metric_id]
        source = metric["source"]
        value = _decimal6(metric["value"])
        reason_codes = ["value_unavailable"] if value is None else []
        result.append({
            "evidence_id": "metric." + metric_id,
            "metric_id": metric_id,
            "value_decimal": value,
            "unit": metric["unit"],
            "source": source,
            "left_value_decimal": _decimal6(metric["left_value"]),
            "right_value_decimal": _decimal6(metric["right_value"]),
            "statistics": {
                "n": metric["statistics"]["n"],
                "mean_decimal": _decimal6(metric["statistics"]["mean"]),
                "median_decimal": _decimal6(metric["statistics"]["median"]),
                "std_decimal": _decimal6(metric["statistics"]["std"]),
                "cv_pct_decimal": _decimal6(metric["statistics"]["cv_pct"]),
            },
            "formula": metric["formula"],
            "source_field": FIRMWARE_METRICS[metric_id]["field"] if source == "firmware" else None,
            "evidence_level": "firmware_measurement" if source == "firmware" else "exploratory",
            "reason_codes": reason_codes,
        })
    return result


def _quality_dto(quality: Mapping[str, object]) -> dict[str, object]:
    status = quality["status"]
    gate = {"complete": "eligible", "usable": "partial", "limited": "withheld"}[status]
    reasons = [] if gate == "eligible" else ["limited_data_quality"]
    if quality["missing_required_values"]:
        reasons.append("missing_required_values")
    return {
        "status": status,
        "gate": gate,
        "total_frames": quality["total_frames"],
        "paired_frames": quality["paired_frames"],
        "paired_frame_rate_pct_decimal": _decimal6(quality["paired_frame_rate_pct"]),
        "missing_required_values": quality["missing_required_values"],
        "reason_codes": reasons,
    }


def _flag_dto(metrics: Mapping[str, Mapping[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "evidence_id": "flag." + flag["metric_key"],
            "metric_id": flag["metric_key"],
            "status": flag["status"],
            "evidence_level": flag["evidence_level"],
            "message": flag["message"],
            "reason_codes": [] if flag["status"] != "unknown" else ["value_unavailable"],
        }
        for flag in build_session_flags(metrics)
    ]


def _pressure_dto(summary: Mapping[str, object]) -> dict[str, object]:
    def sensor(source):
        return {
            "mean_adc_decimal": _decimal6(source["mean_adc"]),
            "valid_samples": source["valid_samples"],
            "total_samples": source["total_samples"],
        }

    bilateral = summary["bilateral"]
    return {
        "method": summary["method"],
        "unit": summary["unit"],
        "threshold_profile": summary["threshold_profile"],
        "left": {"sensors": {key: sensor(value) for key, value in summary["left"]["sensors"].items()}},
        "right": {"sensors": {key: sensor(value) for key, value in summary["right"]["sensors"].items()}},
        "matched_sensors": {
            key: {
                "difference_adc_decimal": _decimal6(value["difference_adc"]),
                "asymmetry_pct_decimal": _decimal6(value["asymmetry_pct"]),
                "higher_side": value["higher_side"],
            }
            for key, value in bilateral["sensors"].items()
        },
        "matched_sensor_count": bilateral["matched_sensor_count"],
        "left_load_proxy_adc_decimal": _decimal6(bilateral["left_load_proxy_adc"]),
        "right_load_proxy_adc_decimal": _decimal6(bilateral["right_load_proxy_adc"]),
        "left_load_share_pct_decimal": _decimal6(bilateral["left_load_share_pct"]),
        "right_load_share_pct_decimal": _decimal6(bilateral["right_load_share_pct"]),
        "load_asymmetry_pct_decimal": _decimal6(bilateral["load_asymmetry_pct"]),
        "attention": summary["attention"],
        "limitation": "pressure_adc_uncalibrated",
    }


def _chart_dto(frames: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if not frames:
        return []
    start = frames[0]["collected_at"]
    return [
        {
            "t_ms": int((frame["collected_at"] - start).total_seconds() * 1000),
            "walking_speed_mps_decimal": _decimal6(snapshot_frame_value(frame, "walking_speed")),
            "step_length_m_decimal": _decimal6(snapshot_frame_value(frame, "step_length")),
            "single_support_time_s_decimal": _decimal6(snapshot_frame_value(frame, "single_support_time")),
            "double_support_time_s_decimal": _decimal6(snapshot_frame_value(frame, "double_support_time")),
            "pressure_left_adc_decimal": None,
            "pressure_right_adc_decimal": None,
            "imu_magnitude_raw_unscaled_decimal": None,
        }
        for frame in frames[:500]
    ]


def _evidence_index(metrics, flags, pressure, quality) -> list[dict[str, str]]:
    pointers = [{"evidence_id": metric["evidence_id"], "field_path": f"/metrics/{index}"}
                for index, metric in enumerate(metrics)]
    pointers.extend({"evidence_id": flag["evidence_id"], "field_path": f"/flags/{index}"}
                    for index, flag in enumerate(flags))
    pointers.append({"evidence_id": "quality.session", "field_path": "/data_quality"})
    if pressure is not None:
        pointers.append({"evidence_id": "pressure.aggregate", "field_path": "/pressure_summary"})
    return pointers


@dataclass(frozen=True)
class AnalyzerFunctions:
    """The four independent nodes; injected only to test scheduling behavior."""

    metrics: Callable[[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]], Mapping[str, object]]
    quality: Callable[[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]], Mapping[str, object]]
    pressure: Callable[[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]], Mapping[str, object]]
    chart: Callable[[Sequence[Mapping[str, object]], Sequence[Mapping[str, object]]], list[dict[str, object]]]

    @classmethod
    def defaults(cls):
        return cls(
            metrics=lambda _rows, frames: aggregate_session(frames),
            quality=lambda _rows, frames: session_data_quality(frames),
            pressure=lambda rows, _frames: summarize_snapshot_pressure_rows(rows),
            chart=lambda _rows, frames: _chart_dto(frames),
        )


class SnapshotPipeline:
    """Build deterministic clinical and Agent payloads without publication side effects."""

    def __init__(self, *, row_loader: Callable[[object], Sequence[Mapping[str, object] | object]] | None = None,
                 analyzers: AnalyzerFunctions | None = None):
        self._row_loader = row_loader or self._load_revision_rows
        self._analyzers = analyzers or AnalyzerFunctions.defaults()

    def build_from_revision(self, revision) -> SnapshotBuildProduct:
        """Perform the one revision-bounded fetch, filter it once, then build."""
        source_rows = self._row_loader(revision)
        return self.build(revision=revision, filtered_rows=source_rows)

    def build(self, *, revision, filtered_rows: Sequence[Mapping[str, object]]) -> SnapshotBuildProduct:
        """Build from the caller's bounded rows; this method never reads the database."""
        self._require_closed_revision(revision)
        raw_rows = self._ordered_source_rows(revision, filtered_rows)
        raw_fingerprint = raw_rows_fingerprint(
            patient_id=revision.patient_id,
            device_id=revision.device_id,
            session_id=revision.session_key,
            rows=raw_rows,
        )
        rows, exclusions = self._filter_rows(revision, raw_rows)
        if not rows:
            raise SnapshotUnavailableError("no_analyzable_rows")
        frames = build_snapshot_frames(rows)
        if not frames:
            raise SnapshotUnavailableError("no_analyzable_frames")
        results, statuses = self._run_independent(rows, frames)
        failed = [name for name in ("metrics", "quality") if statuses[name].state == "failed"]
        if failed:
            raise SnapshotUnavailableError(failed[0] + "_failed")

        metrics = _metric_dto(results["metrics"]["metrics"])
        quality = _quality_dto(results["quality"])
        flags = _flag_dto(results["metrics"]["metrics"])
        pressure = _pressure_dto(results["pressure"]) if statuses["pressure"].state != "failed" else None
        chart = results["chart"] if statuses["chart"].state != "failed" else []
        evidence, evidence_status = self._run_evidence_index(metrics, flags, pressure, quality)
        statuses["evidence_index"] = evidence_status
        limitations = ["pressure_adc_uncalibrated"]
        if quality["gate"] == "withheld":
            limitations.append("data_quality_withheld")
        if statuses["pressure"].state == "failed":
            limitations.append("pressure_unavailable")
        if statuses["chart"].state == "failed":
            limitations.append("chart_unavailable")

        status_mapping = {
            "spatiotemporal": statuses["metrics"].state,
            "data_quality": statuses["quality"].state,
            "pressure": statuses["pressure"].state,
        }
        session = self._session_dto(revision, raw_fingerprint)
        full = {
            "patient_id": revision.patient_id,
            "session_id": revision.session_key,
            "provenance": {
                "snapshot_schema_version": "1",
                "analyzer_set_version": "snapshot-pipeline-v1",
                "threshold_profile_version": "pressure_asymmetry_research_v1",
                "closure_policy_version": revision.closure_policy_version,
            },
            "data_quality": quality,
            "exclusions": [{"reason_code": reason, "count": count}
                           for reason, count in sorted(exclusions.items())],
            "flags": flags,
            "metrics": metrics,
            "pressure_summary": pressure,
            "evidence_index": evidence,
            "analyzer_statuses": status_mapping,
            "limitations": limitations,
            "schema_version": "1",
            "session_revision_id": revision.id,
            "session": session,
            "chart_series": chart,
        }
        full["content_hash"] = self._hash_without(full, "content_hash")
        projection = {
            key: full[key]
            for key in (
                "patient_id", "session_id", "provenance", "data_quality", "exclusions", "flags",
                "metrics", "pressure_summary", "evidence_index", "analyzer_statuses", "limitations",
            )
        }
        projection["projection_schema_version"] = "1"
        projection["snapshot_content_hash"] = full["content_hash"]
        projection["projection_content_hash"] = self._hash_without(
            projection, "projection_content_hash"
        )
        validate_build_product(full_snapshot=full, agent_projection=projection)
        return SnapshotBuildProduct(
            full_snapshot=full,
            agent_projection=projection,
            analyzer_statuses=tuple(statuses[name] for name in _ANALYZER_ORDER),
        )

    @staticmethod
    def _hash_without(payload: Mapping[str, object], field: str) -> str:
        return sha256_hex(canonical_json_bytes({key: value for key, value in payload.items() if key != field}))

    @staticmethod
    def _require_closed_revision(revision) -> None:
        if revision.state != "closed_by_inactivity":
            raise SnapshotUnavailableError("revision_not_closed")

    @staticmethod
    def _ordered_source_rows(revision, source_rows):
        normalized = [_as_mapping(row) for row in source_rows]
        for row in normalized:
            missing = [column for column in _SOURCE_COLUMNS if column not in row]
            if missing:
                raise SnapshotUnavailableError("source_row_missing_fields")
            if row["patient_id"] != revision.patient_id or row["device_id"] != revision.device_id:
                raise SnapshotUnavailableError("revision_scope_mismatch")
        return tuple(sorted(normalized, key=lambda row: (row["collected_at"], row["id"])))

    @staticmethod
    def _filter_rows(revision, raw_rows):
        exclusions = Counter()
        filtered = []
        for raw in raw_rows:
            if raw["foot"] not in {"L", "R"}:
                exclusions["invalid_foot"] += 1
                continue
            row = dict(raw)
            for column in _NUMERIC_COLUMNS:
                if not _finite(row[column]):
                    exclusions["non_finite_numeric"] += 1
                    row[column] = None
            filtered.append(MappingProxyType(row))
        return tuple(filtered), exclusions

    def _run_independent(self, rows, frames):
        functions = {
            "metrics": self._analyzers.metrics,
            "quality": self._analyzers.quality,
            "pressure": self._analyzers.pressure,
            "chart": self._analyzers.chart,
        }
        results: dict[str, Any] = {}
        statuses: dict[str, AnalyzerStatus] = {}
        with ThreadPoolExecutor(max_workers=len(functions)) as executor:
            futures = {
                name: executor.submit(function, rows, frames)
                for name, function in functions.items()
            }
            for name in ("metrics", "quality", "pressure", "chart"):
                try:
                    results[name] = futures[name].result()
                    state = "empty" if name == "chart" and not results[name] else "success"
                    statuses[name] = AnalyzerStatus(name, state, name in {"metrics", "quality"})
                except Exception:
                    statuses[name] = AnalyzerStatus(
                        name, "failed", name in {"metrics", "quality"}, name + "_failed"
                    )
        return results, statuses

    @staticmethod
    def _run_evidence_index(metrics, flags, pressure, quality):
        try:
            return _evidence_index(metrics, flags, pressure, quality), AnalyzerStatus(
                "evidence_index", "success", False
            )
        except Exception:
            return [], AnalyzerStatus("evidence_index", "failed", False, "evidence_index_failed")

    @staticmethod
    def _session_dto(revision, raw_fingerprint):
        closure = json.loads(revision.closure_evidence_canonical)
        reason = closure["reason"]
        if reason == "later_accepted_row_gap":
            reason = "later_accepted_row"
        return {
            "start_at": _timestamp(revision.event_start_at),
            "end_at": _timestamp(revision.event_end_at),
            "first_row_id": revision.first_row_id,
            "last_row_id": revision.last_row_id,
            "row_count": revision.row_count,
            "last_accepted_row_id": revision.last_accepted_row_id,
            "raw_data_fingerprint": raw_fingerprint,
            "closure": {
                "state": "closed_by_inactivity",
                "closed_at": _timestamp(revision.closed_at),
                "policy_version": closure["policy_version"],
                "gap_ms": int(Decimal(closure["idle_seconds"]) * 1000),
                "reason": reason,
                "evidence_at": _timestamp(datetime.fromisoformat(closure["observed_at"])),
                "next_row_id": closure["next_accepted_row_id"],
            },
        }

    @staticmethod
    def _load_revision_rows(revision):
        from models.models import DeviceRawData

        row_ids = json.loads(revision.ordered_row_ids_canonical)
        rows = (
            DeviceRawData.query.filter(
                DeviceRawData.patient_id == revision.patient_id,
                DeviceRawData.device_id == revision.device_id,
                DeviceRawData.id.in_(row_ids),
            )
            .order_by(DeviceRawData.collected_at.asc(), DeviceRawData.id.asc())
            .all()
        )
        if [row.id for row in rows] != row_ids:
            raise SnapshotUnavailableError("revision_row_set_mismatch")
        return rows
