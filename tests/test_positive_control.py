"""Positive control: if a real signal exists, the training code must find it.

A weak result on real filings is only informative if this passes, i.e. the model
code is capable of recovering signal when it is there.
"""
import numpy as np
import pandas as pd
import pytest

from src.features.columns import FEATURE_COLUMNS
from src.training.evaluate_uncertainty import bootstrap_ci
from src.training.train import build_models, evaluate, time_cv_auc

CFG = {"random_state": 0, "logreg": {"C": 1.0},
       "xgboost": {"n_estimators": 80, "max_depth": 2, "learning_rate": 0.1,
                   "subsample": 0.9, "colsample_bytree": 0.9}}


def planted_signal(n=400, seed=3):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame(rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    logit = 1.5 * X["unc_ratio"] - 1.0 * X["tfidf_similarity"]
    y = pd.Series((logit + rng.normal(scale=0.5, size=n) > 0).astype(int))
    return X, y


@pytest.mark.parametrize("name", ["logistic_regression", "xgboost"])
def test_models_recover_planted_signal(name):
    X, y = planted_signal()
    Xtr, ytr, Xte, yte = X[:300], y[:300], X[300:], y[300:]
    model = build_models(CFG)[name]
    assert time_cv_auc(model, Xtr, ytr, 3) > 0.8
    model.fit(Xtr, ytr)
    assert evaluate(model, Xte, yte)["roc_auc"] > 0.8


def test_bootstrap_ci_separates_signal_from_noise():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 60)
    good = bootstrap_ci(y, y * 0.6 + rng.uniform(0, 0.4, 60))
    noise = bootstrap_ci(y, rng.uniform(size=60))
    assert good["auc_ci_low"] > 0.5 and not good["auc_ci_includes_0.5"]
    assert noise["auc_ci_includes_0.5"]
