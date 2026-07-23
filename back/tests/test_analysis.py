import api.analysis as analysis_module
from api.analysis import analyze


def test_analyze_returns_five_floats():
    t = analyze(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert len(t) == 5
    assert all(isinstance(x, float) for x in t)


def test_fallback_model_has_both_classes_for_every_output(tmp_path, monkeypatch):
    def single_class_labels(*args, **kwargs):
        return analysis_module.np.zeros(kwargs["size"], dtype=int)

    monkeypatch.setattr(analysis_module.np.random, "randint", single_class_labels)

    model = analysis_module._load_or_train_model(tmp_path / "missing-model.pkl")

    assert len(model.estimators_) == 5
    assert all(set(estimator.classes_) == {0, 1} for estimator in model.estimators_)
