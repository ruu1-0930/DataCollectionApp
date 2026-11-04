"""Diagnostic facts for existing formulas; does not filter, score or alter values."""
from collections import Counter

from services.gait_analysis import _finite_or_none, _frame_value, _safe_ratio, _side_mean


def _observations(frames, fields):
    negative, incomplete = 0, 0
    for frame in frames:
        values = [(frame.get(side) or {}).get(field) for side in ('L', 'R') for field in fields]
        finite = [_finite_or_none(value) for value in values]
        negative += any(value is not None and value < 0 for value in finite)
        incomplete += any(value is None for value in finite)
    return {'negative_source_frames': negative, 'incomplete_bilateral_fields': incomplete}


def _ratio_diagnostic(frames, numerator_field, denominator_fields, multiplier, *, variation=False):
    exclusions, inputs = Counter(), []
    for frame in frames:
        numerator = _frame_value(frame, numerator_field)
        parts = [_frame_value(frame, field) for field in denominator_fields]
        if numerator is None or any(part is None for part in parts):
            exclusions['missing_operand'] += 1
            continue
        denominator = sum(parts)
        if denominator == 0:
            exclusions['zero_denominator'] += 1
            continue
        value = _safe_ratio(numerator, denominator, multiplier)
        if value is None:
            exclusions['non_finite_result'] += 1
            continue
        inputs.append(value)
    observations = _observations(frames, tuple(dict.fromkeys((numerator_field, *denominator_fields))))
    if variation:
        observations['nonpositive_period_frames'] = sum(value <= 0 for value in inputs)
    return dict(total_frames=len(frames), formula_input_count=len(inputs),
        excluded_frame_count=len(frames)-len(inputs), exclusions=dict(exclusions),
        observations=observations,
        state=('insufficient_variation_inputs' if len(inputs) < 2 else 'available') if variation
              else ('available' if inputs else 'unavailable'))


def _asymmetry_diagnostic(frames):
    counts = {side: sum(_finite_or_none((frame.get(side) or {}).get('step_length')) is not None
                        for frame in frames) for side in ('L', 'R')}
    paired = sum(all(_finite_or_none((frame.get(side) or {}).get('step_length')) is not None
                     for side in ('L', 'R')) for frame in frames)
    left, right = (_side_mean(frames, side, 'step_length') for side in ('L', 'R'))
    reason = None
    if left is None or right is None:
        reason = 'missing_bilateral_mean'
    else:
        denominator, difference = _finite_or_none(left+right), _finite_or_none(abs(left-right))
        if denominator == 0:
            reason = 'zero_denominator'
        elif denominator is None or difference is None or _safe_ratio(difference, denominator/2, 100) is None:
            reason = 'non_finite_result'
    return dict(total_frames=len(frames), left_input_count=counts['L'], right_input_count=counts['R'],
        paired_input_count=paired, formula_input_count=int(reason is None),
        comparison_exclusions={} if reason is None else {reason: 1},
        observations=_observations(frames, ('step_length',)),
        state='available' if reason is None else 'unavailable')


def analyze_derivation_quality(frames):
    """Count actual formula cohorts, separately from suspect source observations.

    For ratios, `available` means finite per-frame inputs exist (at least two
    for variation), not that the final aggregate exists: aggregation can still
    overflow. It never means clinically validated. Asymmetry's formula input
    is one comparison of two independent means, not a per-frame series.
    Non-finite source values have the same missing-operand semantics as the old
    aggregator; diagnostics do not claim to distinguish pre-filtered causes.
    """
    frames = tuple(frames)
    return {'version': 1, 'metrics': {
        'cadence_spm': _ratio_diagnostic(frames, 'walking_speed', ('step_length',), 60),
        'stride_time_cv_pct': _ratio_diagnostic(frames, 'step_length', ('walking_speed',), 2, variation=True),
        'double_support_ratio_pct': _ratio_diagnostic(frames, 'double_support_time',
            ('single_support_time', 'double_support_time'), 100),
        'step_length_asymmetry_pct': _asymmetry_diagnostic(frames),
    }}
