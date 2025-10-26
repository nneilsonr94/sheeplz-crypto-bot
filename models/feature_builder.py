"""Feature builder utilities used by the 1-minute trainer and live runtime.

This module provides a single-row feature constructor that mirrors the
`build_features` logic in `models/train_1min.py`. Keeping it separate makes
it easy to reuse the exact same feature transformation at runtime.
"""
from __future__ import annotations
from typing import List, Dict
import numpy as np
from integrations.indicators_tv import (
    watchtower_signal,
    believe_it_meter,
    livermore_3_points,
    auto_fib_levels,
)


def build_feature_from_window(window_closes: List[float]) -> np.ndarray:
    """Given a list of closes of length `window`, return a 1-D feature array
    matching the training-time column order used in `models/train_1min.py`.

    Returns
    -------
    np.ndarray
        Shape (n_features,) ready to be passed to a scikit-learn/LightGBM
        predictor instance.
    """
    window = len(window_closes)
    if window < 2:
        raise ValueError("window_closes must contain at least 2 values")

    returns = np.diff(window_closes) / np.array(window_closes[:-1])
    feat = list(returns[-(window-1):])

    wt = watchtower_signal(window_closes)
    wt_val = 1.0 if wt == 'buy' else (-1.0 if wt == 'sell' else 0.0)
    bim = believe_it_meter(window_closes)
    liv = livermore_3_points(window_closes)
    liv_val = 1.0 if liv == 'buy' else (-1.0 if liv == 'sell' else 0.0)
    fib = auto_fib_levels(window_closes)
    last = window_closes[-1]
    fib_618 = fib.get('0.618', last)
    fib_382 = fib.get('0.382', last)
    feat.extend([wt_val, bim, liv_val, (last - fib_618), (last - fib_382)])

    return np.array(feat, dtype=float)
