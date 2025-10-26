import os
import joblib
import numpy as np

# ensure project root is importable when tests run from pytest
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from models.feature_builder import build_feature_from_window


def test_model_inference_and_action_range():
    model_path = os.getenv('MODEL_1MIN_PATH', 'models/lgbm_1min.pkl')
    assert os.path.exists(model_path), f"Model not found at {model_path}"
    model = joblib.load(model_path)

    # build a synthetic window matching the default window size used in config
    window_size = 20
    # simple synthetic price series slowly increasing
    window = [100.0 + 0.01 * i for i in range(window_size)]
    feat = build_feature_from_window(window)
    Xf = feat.reshape(1, -1)

    # predict_proba must exist and return two-class probabilities
    probs = model.predict_proba(Xf)
    assert probs.shape == (1, 2)
    prob = float(probs[0][1])

    # compute model action (same mapping as runtime)
    model_action = float((prob - 0.5) * 2.0)
    assert -1.0 <= model_action <= 1.0


if __name__ == '__main__':
    test_model_inference_and_action_range()
    print('OK')
