"""Assemble the labelled dataset and the time-based train/test split."""

from typing import Dict, Tuple

import pandas as pd

KEYS = ["ticker", "accession"]
MIN_ROWS = 20


def build_dataset(features: pd.DataFrame, labels: pd.DataFrame, split: Dict) -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    """Return (train, test, info).

    Only filings that have a prior-year filing AND a label are usable. Train =
    filings up to (test_start - embargo); test = filings from test_start on.
    Filings inside the embargo window are dropped so no training label window
    overlaps the test period.
    """
    features = features.copy()
    features["filing_date"] = pd.to_datetime(features["filing_date"])
    lab = labels[KEYS + ["labeled", "target", "abnormal_ret"]]
    merged = features.merge(lab, on=KEYS, how="left")
    eligible = merged[merged["has_prior"].astype(bool) & merged["labeled"].fillna(False).astype(bool)].copy()
    eligible["target"] = eligible["target"].astype(int)

    test_start = pd.Timestamp(split["test_start_date"])
    train_end = test_start - pd.Timedelta(days=split["embargo_days"])
    train = eligible[eligible["filing_date"] <= train_end].sort_values("filing_date")
    test = eligible[eligible["filing_date"] >= test_start].sort_values("filing_date")
    embargoed = int(((eligible["filing_date"] > train_end) & (eligible["filing_date"] < test_start)).sum())

    for name, part in (("train", train), ("test", test)):
        if len(part) < MIN_ROWS:
            raise ValueError(
                f"{name} set has only {len(part)} rows (need >= {MIN_ROWS}); " "check split dates in params.yaml"
            )
        if part["target"].nunique() < 2:
            raise ValueError(f"{name} set contains a single class; cannot evaluate")

    info = {
        "n_total_filings": int(len(features)),
        "n_eligible": int(len(eligible)),
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "n_embargoed": embargoed,
        "train_end": str(train_end.date()),
        "test_start": str(test_start.date()),
        "train_positive_rate": float(train["target"].mean()),
        "test_positive_rate": float(test["target"].mean()),
    }
    return train, test, info
