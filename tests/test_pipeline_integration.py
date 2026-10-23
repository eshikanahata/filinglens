"""Run the labels and features stages end to end on synthetic parsed filings."""

import json

import numpy as np
import pandas as pd
import pytest

from src.features import build_features
from src.features.columns import FEATURE_COLUMNS
from src.labels import make_labels

PARAMS = {
    "prices": {"benchmark": "SPY"},
    "labels": {"horizon_trading_days": 30},
    "split": {"test_start_date": "2025-07-01", "embargo_days": 45},
    "features": {
        "lm_dictionary_path": "lm.csv",
        "min_prior_gap_days": 300,
        "max_prior_gap_days": 450,
        "tfidf": {"max_features": 500, "min_df": 2, "ngram_range": [1, 2]},
    },
}
VOCAB = [
    "supply",
    "chain",
    "regulation",
    "litigation",
    "cyber",
    "inflation",
    "customers",
    "competition",
    "currency",
    "interest",
    "tax",
    "climate",
    "labor",
    "pandemic",
]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(1)
    tickers = [f"T{i}" for i in range(6)]
    for t in tickers:
        for year in range(2021, 2027):
            words = rng.choice(VOCAB + ["loss", "may", "lawsuit", "gain"], size=900)
            text = ". ".join(" ".join(words[i : i + 12]) for i in range(0, 900, 12)) + "."
            rec = {
                "ticker": t,
                "accession": f"{t}-{year}",
                "filing_date": f"{year}-02-10",
                "report_date": f"{year - 1}-12-31",
                "risk_factors": text,
                "risk_words": len(text.split()),
                "full_words": len(text.split()) * 5,
            }
            d = tmp_path / "data/parsed" / t
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{rec['accession']}.json").write_text(json.dumps(rec))
    idx = pd.bdate_range("2020-12-01", "2026-10-14")
    prices = pd.DataFrame(
        {s: 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))) for s in tickers + ["SPY"]}, index=idx
    )
    prices.index.name = "date"
    (tmp_path / "data/prices").mkdir(parents=True)
    prices.to_csv(tmp_path / "data/prices/prices.csv")
    (tmp_path / "lm.csv").write_text(
        "Word,Negative,Positive,Uncertainty,Litigious\nLOSS,1,0,0,0\nGAIN,0,1,0,0\n"
        "MAY,0,0,1,0\nLAWSUIT,0,0,0,1\nLITIGATION,0,0,0,1\n"
    )
    for mod in (make_labels, build_features):
        monkeypatch.setattr(mod, "load_params", lambda *a, **k: PARAMS)
    return tmp_path


def test_labels_then_features(workspace):
    make_labels.main()
    labels = pd.read_csv(workspace / "data/labels/labels.csv")
    assert len(labels) == 36 and labels["labeled"].all()
    assert set(labels["target"].unique()) <= {0, 1}

    build_features.main()
    feats = pd.read_csv(workspace / "data/features/features.csv")
    assert len(feats) == 36
    assert list(feats.columns[-len(FEATURE_COLUMNS) :]) == FEATURE_COLUMNS
    first = feats[feats["accession"].str.endswith("2021")]
    later = feats[~feats["accession"].str.endswith("2021")]
    assert not first["has_prior"].any() and later["has_prior"].all()
    assert later["tfidf_similarity"].between(0, 1).all()
    assert later["risk_words_change"].notna().all()
    assert first["tfidf_similarity"].isna().all()
    assert (workspace / "data/features/tfidf_vectorizer.joblib").exists()
