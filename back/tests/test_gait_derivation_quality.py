"""Input-count diagnostics follow the existing formulas, without changing them."""
from copy import deepcopy

import pytest

from services.gait_analysis import _ratio_series, aggregate_session
from services.gait_derivation_quality import analyze_derivation_quality


def frame(**changes):
    side = dict(walking_speed=1.2, step_length=.6, single_support_time=.4, double_support_time=.1)
    side.update(changes)
    return {'L': side.copy(), 'R': side.copy()}


def test_period_input_count_is_not_the_final_cv_summary_count():
    frames = [frame() for _ in range(20)]
    d = analyze_derivation_quality(frames)
    assert d['version'] == 1
    assert d['metrics']['stride_time_cv_pct']['formula_input_count'] == 20
    assert aggregate_session(frames)['metrics']['stride_time_cv_pct']['statistics']['n'] == 1


def test_single_period_and_zero_mixture_do_not_establish_variation():
    frames = [frame()] + [frame(walking_speed=0, step_length=0) for _ in range(19)]
    cv = analyze_derivation_quality(frames)['metrics']['stride_time_cv_pct']
    assert cv['formula_input_count'] == 1
    assert cv['excluded_frame_count'] == 19
    assert cv['exclusions'] == {'zero_denominator': 19}
    assert cv['state'] == 'insufficient_variation_inputs'
    assert aggregate_session(frames)['metrics']['stride_time_cv_pct']['value'] == 0


@pytest.mark.parametrize('frames', [[], [frame()], [frame(walking_speed=.000001), frame()],
    [frame(walking_speed=0, step_length=0)], [frame(step_length=None)],
    [frame(walking_speed=float('inf'))]])
def test_formula_counts_match_current_ratio_functions(frames):
    original = deepcopy(frames)
    result = analyze_derivation_quality(frames)
    for key, numerator, denominator, multiplier in [
        ('cadence_spm', 'walking_speed', 'step_length', 60),
        ('stride_time_cv_pct', 'step_length', 'walking_speed', 2)]:
        item = result['metrics'][key]
        assert item['formula_input_count'] == len(_ratio_series(frames, numerator, denominator, multiplier))
        assert item['formula_input_count'] + item['excluded_frame_count'] == len(frames)
        assert sum(item['exclusions'].values()) == item['excluded_frame_count']
    assert result['metrics']['double_support_ratio_pct']['formula_input_count'] == aggregate_session(frames)['metrics']['double_support_ratio_pct']['statistics']['n']
    assert result['metrics']['step_length_asymmetry_pct']['formula_input_count'] == aggregate_session(frames)['metrics']['step_length_asymmetry_pct']['statistics']['n']
    assert frames == original


def test_negative_and_cross_side_inputs_are_observations_not_silent_exclusions():
    negative, mixed = frame(), frame()
    negative['L']['step_length'], negative['R']['step_length'] = -1., 2.2
    mixed['L']['walking_speed'], mixed['R']['step_length'] = None, None
    result = analyze_derivation_quality([negative, mixed])['metrics']
    assert result['cadence_spm']['formula_input_count'] == 2
    assert result['cadence_spm']['observations']['negative_source_frames'] == 1
    assert result['cadence_spm']['observations']['incomplete_bilateral_fields'] == 1
    asym = result['step_length_asymmetry_pct']
    assert (asym['left_input_count'], asym['right_input_count'], asym['paired_input_count']) == (2, 1, 1)
    assert asym['formula_input_count'] == 1  # one session-mean comparison


def test_support_ratio_counts_and_overflow_are_explicit():
    frames = [frame(), frame(single_support_time=0, double_support_time=0),
              frame(single_support_time=None), frame(single_support_time=1e308, double_support_time=1e308)]
    # Keep operand means finite; overflow must occur in the denominator sum.
    frames[-1]['R'] = None
    support = analyze_derivation_quality(frames)['metrics']['double_support_ratio_pct']
    assert support['formula_input_count'] == 1
    assert support['exclusions'] == {'zero_denominator': 1, 'missing_operand': 1, 'non_finite_result': 1}


def test_disjoint_side_windows_are_visible_even_when_asymmetry_is_calculable():
    left, right = frame(), frame()
    left['R'], right['L'] = None, None
    asym = analyze_derivation_quality([left, right])['metrics']['step_length_asymmetry_pct']
    assert asym['formula_input_count'] == 1 and asym['paired_input_count'] == 0
    assert asym['left_input_count'] == asym['right_input_count'] == 1
    assert asym['observations']['incomplete_bilateral_fields'] == 2


def test_near_zero_denominator_is_not_removed_by_an_invented_threshold():
    cv = analyze_derivation_quality([frame(walking_speed=.000001), frame()])['metrics']['stride_time_cv_pct']
    assert cv['formula_input_count'] == 2 and cv['excluded_frame_count'] == 0
    assert cv['state'] == 'available'


def test_zero_periods_are_observed_without_silently_filtering_the_old_formula():
    frames = [frame(step_length=0), frame()]
    cv = analyze_derivation_quality(frames)['metrics']['stride_time_cv_pct']
    assert cv['formula_input_count'] == 2
    assert cv['observations']['nonpositive_period_frames'] == 1
