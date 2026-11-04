"""Internal contracts for a snapshot build before T04 publication."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator


SNAPSHOT_ANALYZER_SET_VERSION = "snapshot-pipeline-v2"
DERIVATION_ANALYZER_SET_VERSION = "snapshot-pipeline-v3"


class SnapshotUnavailableError(RuntimeError):
    """A required analyzer or source gate prevented a build product."""


@dataclass(frozen=True)
class AnalyzerStatus:
    name: str
    state: str
    required: bool
    reason_code: str | None = None


@dataclass(frozen=True)
class SnapshotBuildProduct:
    """Validated clinical payloads awaiting T04 transactional publication."""

    full_snapshot: Mapping[str, object]
    agent_projection: Mapping[str, object]
    analyzer_statuses: tuple[AnalyzerStatus, ...]


def _validator(definition_name: str) -> Draft202012Validator:
    version = '2' if definition_name.endswith('V2') else '1'
    schema_path = Path(__file__).parents[1] / "contracts" / f"gait_snapshot_v{version}.schema.json"
    document = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator({**document, "$ref": "#/$defs/" + definition_name})


def validate_build_product(*, full_snapshot: Mapping[str, object],
                           agent_projection: Mapping[str, object]) -> None:
    """Reject an incomplete internal build before it reaches T04 persistence."""
    version = full_snapshot.get('schema_version')
    if version not in {'1', '2'} or agent_projection.get('projection_schema_version') != version:
        raise ValueError('unsupported_snapshot_version_pair')
    _validator(f"SnapshotBuildFullV{version}").validate(full_snapshot)
    _validator(f"SnapshotBuildAgentProjectionV{version}").validate(agent_projection)
    if version == '2':
        for payload in (full_snapshot, agent_projection):
            _validate_derivation_counts(payload)


def _validate_derivation_counts(payload):
    total = payload['data_quality']['total_frames']
    for key, item in payload['derivation_quality']['metrics'].items():
        if item['total_frames'] != total or any(n > total for n in item['observations'].values()):
            raise ValueError('invalid_derivation_counts')
        count = item['formula_input_count']
        if key == 'step_length_asymmetry_pct':
            left, right, paired = item['left_input_count'], item['right_input_count'], item['paired_input_count']
            if (not max(0, left+right-total) <= paired <= min(left, right)
                    or max(item['left_input_count'], item['right_input_count']) > total
                    or item['observations']['incomplete_bilateral_fields'] != total-paired
                    or (count == 1 and (left == 0 or right == 0))
                    or sum(item['comparison_exclusions'].values()) != 1-count
                    or item['state'] != ('available' if count else 'unavailable')):
                raise ValueError('invalid_derivation_counts')
        else:
            expected = ('available' if count >= 2 else 'insufficient_variation_inputs') if key == 'stride_time_cv_pct' else ('available' if count else 'unavailable')
            if (count + item['excluded_frame_count'] != total
                    or sum(item['exclusions'].values()) != item['excluded_frame_count']
                    or item['state'] != expected):
                raise ValueError('invalid_derivation_counts')
            if key == 'stride_time_cv_pct' and item['observations']['nonpositive_period_frames'] > count:
                raise ValueError('invalid_derivation_counts')
