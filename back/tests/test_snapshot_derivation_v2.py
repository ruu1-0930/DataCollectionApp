"""Opt-in V2 binds diagnostics to immutable values; V1 stays readable."""
from copy import deepcopy
from dataclasses import replace

import pytest
from jsonschema import ValidationError

from config import db
from models.models import AnalysisSnapshot
from services.snapshot_contracts import SnapshotUnavailableError, validate_build_product
from services.snapshot_pipeline import SnapshotPipeline
from services.snapshot_repository import SnapshotVersions
from .test_snapshot_pipeline import revision, rows
from .test_analysis_snapshot_service import scope, service, ensure, read


def versions2():
    return SnapshotVersions(snapshot_schema_version='2', projection_schema_version='2',
        analyzer_set_version='snapshot-pipeline-v3')


def test_new_build_hashes_diagnostics_and_preserves_old_metric_values():
    source = rows()
    before = deepcopy(source)
    old = SnapshotPipeline().build(revision=revision(), filtered_rows=source)
    new = SnapshotPipeline(schema_version='2').build(revision=revision(), filtered_rows=source)
    assert new.full_snapshot['schema_version'] == new.agent_projection['projection_schema_version'] == '2'
    assert new.full_snapshot['provenance']['analyzer_set_version'] == 'snapshot-pipeline-v3'
    assert new.full_snapshot['metrics'] == old.full_snapshot['metrics']
    diagnostic = new.full_snapshot['derivation_quality']
    assert diagnostic == new.agent_projection['derivation_quality']
    assert diagnostic['metrics']['stride_time_cv_pct']['formula_input_count'] == 2
    assert any(e['field_path'] == '/derivation_quality' for e in new.agent_projection['evidence_index'])
    changed = deepcopy(dict(new.full_snapshot))
    changed['derivation_quality']['metrics']['stride_time_cv_pct']['formula_input_count'] = 1
    assert SnapshotPipeline._hash_without(changed, 'content_hash') != new.full_snapshot['content_hash']
    assert 'derivation_quality' not in old.full_snapshot and source == before


def test_new_diagnostics_use_the_filtered_frozen_frames():
    source = rows()
    source[0]['walking_speed'] = float('inf')
    product = SnapshotPipeline(schema_version='2').build(revision=revision(), filtered_rows=source)
    cadence = product.full_snapshot['derivation_quality']['metrics']['cadence_spm']
    assert cadence['formula_input_count'] == 2
    assert cadence['observations']['incomplete_bilateral_fields'] == 1
    assert product.full_snapshot['exclusions'] == [{'reason_code': 'non_finite_numeric', 'count': 1}]


def test_required_diagnostic_failure_is_not_silently_omitted(monkeypatch):
    def failure(_frames):
        raise RuntimeError('synthetic diagnostic failure')
    monkeypatch.setattr('services.snapshot_pipeline.analyze_derivation_quality', failure)
    with pytest.raises(SnapshotUnavailableError, match='^derivation_quality_failed$'):
        SnapshotPipeline(schema_version='2').build(revision=revision(), filtered_rows=rows())


def test_legal_disjoint_step_length_windows_remain_readable():
    source = rows()
    source[0]['step_length'] = None
    source[3]['step_length'] = None
    built = SnapshotPipeline(schema_version='2').build(revision=revision(), filtered_rows=source)
    item = built.full_snapshot['derivation_quality']['metrics']['step_length_asymmetry_pct']
    assert (item['left_input_count'], item['right_input_count'], item['paired_input_count']) == (1, 1, 0)
    assert item['formula_input_count'] == 1


def test_v2_default_producer_rejects_wrong_analyzer_before_build(scope):
    with pytest.raises(ValueError, match='unsupported_analyzer_version'):
        service(versions=replace(versions2(), analyzer_set_version='snapshot-pipeline-v2'))


def test_v2_publishes_reuses_and_reads_both_versions_without_rewriting_v1(scope):
    old_service = service()
    old = ensure(old_service, scope)
    original = db.session.get(AnalysisSnapshot, str(old.snapshot_id)).canonical_payload
    db.session.remove()
    new_service = service(versions=versions2())
    new = ensure(new_service, scope)
    assert new.created and new.snapshot_id != old.snapshot_id
    assert not ensure(new_service, scope).created
    assert read(new_service, scope, old.snapshot_id).snapshot['schema_version'] == '1'
    assert read(new_service, scope, old.snapshot_id, True).projection['projection_schema_version'] == '1'
    full = read(new_service, scope, new.snapshot_id).snapshot
    projection = read(new_service, scope, new.snapshot_id, True).projection
    assert full['derivation_quality'] == projection['derivation_quality']
    assert projection['snapshot_content_hash'] == full['content_hash']
    assert db.session.get(AnalysisSnapshot, str(old.snapshot_id)).canonical_payload == original


@pytest.mark.parametrize('change', ['unknown_field', 'boolean_count', 'inconsistent_count', 'missing_diagnostics',
    'impossible_overlap', 'empty_side_comparison', 'inconsistent_observation'])
def test_v2_contract_rejects_bad_diagnostic_payloads(change):
    product = SnapshotPipeline(schema_version='2').build(revision=revision(), filtered_rows=rows())
    full, projection = deepcopy(dict(product.full_snapshot)), deepcopy(dict(product.agent_projection))
    if change == 'missing_diagnostics':
        del full['derivation_quality']
    elif change in {'impossible_overlap', 'empty_side_comparison', 'inconsistent_observation'}:
        item = full['derivation_quality']['metrics']['step_length_asymmetry_pct']
        if change == 'impossible_overlap': item['paired_input_count'] = 0
        elif change == 'empty_side_comparison':
            item.update(left_input_count=0, paired_input_count=0)
            item['observations']['incomplete_bilateral_fields'] = item['total_frames']
        else: item['observations']['incomplete_bilateral_fields'] = 1
    else:
        item = full['derivation_quality']['metrics']['cadence_spm']
        if change == 'unknown_field': item['unknown'] = 1
        elif change == 'boolean_count': item['formula_input_count'] = True
        else: item['formula_input_count'] = 99
    with pytest.raises((ValidationError, ValueError)):
        validate_build_product(full_snapshot=full, agent_projection=projection)
