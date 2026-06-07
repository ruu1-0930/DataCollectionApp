import os
import pickle
import numpy as np
from sklearn.svm import SVC
from sklearn.multioutput import MultiOutputClassifier

_MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'my_svm_model.pkl')


def _load_or_train_model(model_path=_MODEL_PATH):
    if os.path.exists(model_path):
        try:
            with open(model_path, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    X_fake = np.random.rand(10, 6)
    y_fake = np.random.randint(0, 2, size=(10, 5))
    m = MultiOutputClassifier(SVC(probability=True))
    m.fit(X_fake, y_fake)
    return m


_model = _load_or_train_model()


def analyze(ax, ay, az, gx, gy, gz):
    """返回 (T1..T5)，取每个输出类别为 1 的概率。"""
    x = np.array([[ax, ay, az, gx, gy, gz]], dtype=np.float32)
    probas = _model.predict_proba(x)
    return tuple(float(probas[i][0][1]) for i in range(5))
