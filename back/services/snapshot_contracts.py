"""Internal contracts for a snapshot build before T04 publication."""

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping

from jsonschema import Draft202012Validator


SNAPSHOT_ANALYZER_SET_VERSION = "snapshot-pipeline-v2"


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
    schema_path = Path(__file__).parents[1] / "contracts" / "gait_snapshot_v1.schema.json"
    document = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator({**document, "$ref": "#/$defs/" + definition_name})


def validate_build_product(*, full_snapshot: Mapping[str, object],
                           agent_projection: Mapping[str, object]) -> None:
    """Reject an incomplete internal build before it reaches T04 persistence."""
    _validator("SnapshotBuildFullV1").validate(full_snapshot)
    _validator("SnapshotBuildAgentProjectionV1").validate(agent_projection)
