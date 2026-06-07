from api.patient import format_subject_id


def test_format_subject_id():
    assert format_subject_id(1) == '#00001'
    assert format_subject_id(427) == '#00427'
    assert format_subject_id(123456) == '#123456'
