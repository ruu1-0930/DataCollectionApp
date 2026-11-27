import pytest

from services.gait_analysis import aggregate_session, snapshot_frame_value


def test_asymmetric_firmware_periods_and_swings_are_interpreted_without_mutation():
    frame = {'L': dict(single_support_time=.35, double_support_time=1.2, walking_speed=.8, step_length=123),
             'R': dict(single_support_time=.45, double_support_time=1.4, walking_speed=1.2, step_length=456)}
    metrics = aggregate_session([frame], corrected=True)['metrics']
    for key, expected in [('single_support_time_s', (.45, .35)), ('double_support_time_s', (.2, .3)),
                          ('step_length_m', (.6, .7))]:
        assert (metrics[key]['left_value'], metrics[key]['right_value']) == pytest.approx(expected)
        assert metrics[key]['source'] == 'derived'
    assert snapshot_frame_value(frame, 'double_support_time', corrected=True) == pytest.approx(.25)
    assert frame['L']['double_support_time'] == 1.2


def test_missing_or_impossible_support_does_not_become_zero():
    foot = dict(single_support_time=.4, double_support_time=.3, walking_speed=1., step_length=999)
    result = aggregate_session([{'L': foot, 'R': None}], corrected=True)['metrics']
    assert result['single_support_time_s']['left_value'] is None
    assert result['single_support_time_s']['right_value'] == .4
    assert result['double_support_time_s']['value'] is None
    assert aggregate_session([{'L': foot, 'R': foot}], corrected=True)['metrics']['double_support_time_s']['value'] is None
