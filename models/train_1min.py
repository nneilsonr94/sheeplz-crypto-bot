"""Train a 1-minute prediction model using ported indicators and simple features.

This script creates a synthetic dataset (or can be adapted to use CSV via
`DataProvider`), computes features from the last N closes, includes the
port indicators, and trains a LightGBM classifier to predict next-minute
direction (up/down). The trained model is saved with joblib.
"""
from __future__ import annotations
import os
import math
from typing import List

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import joblib
import lightgbm as lgb

import sys, os
# ensure project root is on sys.path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from integrations.indicators_tv import (
    watchtower_signal,
    bot_activity_idiot_light,
    believe_it_meter,
    livermore_3_points,
    auto_fib_levels,
)


def make_synthetic_ohlcv(n=500):
    import math
    data = []
    for i in range(n):
        price = 100 + 2 * math.sin(i * 0.1) + 0.1 * math.sin(i * 0.03)
        open_p = price + (0.01 if i % 2 == 0 else -0.01)
        close_p = price
        high = max(open_p, close_p) + 0.1
        low = min(open_p, close_p) - 0.1
        volume = 100 + (50 if i % 30 == 0 else 0)
        data.append({'open': open_p, 'high': high, 'low': low, 'close': close_p, 'volume': volume})
    return pd.DataFrame(data)


def build_features(df: pd.DataFrame, window: int = 20) -> (pd.DataFrame, pd.Series):
    closes = df['close'].tolist()
    vols = df['volume'].tolist()
    X = []
    y = []
    for i in range(window, len(df)-1):
        window_closes = closes[i-window:i]
        window_vols = vols[i-window:i]
        # features: flattened relative returns
        returns = np.diff(window_closes) / window_closes[:-1]
        feat = list(returns[-(window-1):])
        # add indicators numeric
        wt = watchtower_signal(window_closes)
        wt_val = 1.0 if wt == 'buy' else (-1.0 if wt == 'sell' else 0.0)
        bim = believe_it_meter(window_closes)
        liv = livermore_3_points(window_closes)
        liv_val = 1.0 if liv == 'buy' else (-1.0 if liv == 'sell' else 0.0)
        fib = auto_fib_levels(window_closes)
        # distance to 0.618 and 0.382
        last = window_closes[-1]
        fib_618 = fib.get('0.618', last)
        fib_382 = fib.get('0.382', last)
        feat.extend([wt_val, bim, liv_val, (last - fib_618), (last - fib_382)])
        # label: next minute return sign
        next_ret = (closes[i+1] - closes[i]) / closes[i]
        label = 1 if next_ret > 0 else 0
        X.append(feat)
        y.append(label)
    X = pd.DataFrame(X)
    y = pd.Series(y)
    return X, y


def train_and_save(model_path: str = 'models/lgbm_1min.pkl'):
    df = make_synthetic_ohlcv(1000)
    X, y = build_features(df, window=20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    clf = lgb.LGBMClassifier(n_estimators=100, learning_rate=0.1)
    clf.fit(X_train, y_train)
    preds = clf.predict(X_test)
    acc = accuracy_score(y_test, preds)
    print('Test accuracy:', acc)
    print(classification_report(y_test, preds))

    os.makedirs(os.path.dirname(model_path) or '.', exist_ok=True)
    joblib.dump(clf, model_path)
    print('Saved model to', model_path)


if __name__ == '__main__':
    train_and_save()
