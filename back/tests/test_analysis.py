from api.analysis import analyze


def test_analyze_returns_five_floats():
    t = analyze(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert len(t) == 5
    assert all(isinstance(x, float) for x in t)
