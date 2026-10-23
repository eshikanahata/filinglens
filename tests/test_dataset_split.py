import numpy as np
import pandas as pd
import pytest

from src.features.columns import FEATURE_COLUMNS
from src.training.dataset import build_dataset

SPLIT = {"test_start_date": "2025-07-01", "embargo_days": 45}


def synthetic(n=200, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime("2022-03-01") + pd.to_timedelta(np.sort(rng.integers(0, 1600, n)), unit="D")
    feats = pd.DataFrame(rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    feats["ticker"] = [f"T{i % 30}" for i in range(n)]
    feats["accession"] = [f"acc{i}" for i in range(n)]
    feats["filing_date"] = dates.date.astype(str)
    feats["report_date"] = feats["filing_date"]
    feats["has_prior"] = True
    labels = feats[["ticker", "accession", "filing_date", "report_date"]].copy()
    labels["labeled"] = True
    labels["abnormal_ret"] = rng.normal(size=n)
    labels["target"] = (labels["abnormal_ret"] < 0).astype(int)
    return feats, labels


def test_split_is_time_ordered_with_embargo():
    feats, labels = synthetic()
    train, test, info = build_dataset(feats, labels, SPLIT)
    assert train["filing_date"].max() <= pd.Timestamp("2025-05-17")
    assert test["filing_date"].min() >= pd.Timestamp("2025-07-01")
    assert train["filing_date"].max() < test["filing_date"].min()
    assert info["n_train"] + info["n_test"] + info["n_embargoed"] == info["n_eligible"]


def test_unlabeled_and_no_prior_rows_excluded():
    feats, labels = synthetic()
    labels.loc[:30, "labeled"] = False
    feats.loc[31:50, "has_prior"] = False
    _, _, info = build_dataset(feats, labels, SPLIT)
    assert info["n_eligible"] == len(feats) - 31 - 20


def test_too_small_split_raises():
    feats, labels = synthetic(n=40)
    with pytest.raises(ValueError, match="rows"):
        build_dataset(feats, labels, SPLIT)
