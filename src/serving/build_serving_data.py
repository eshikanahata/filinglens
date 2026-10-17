"""DVC stage `serving_data`: precompute everything the backend needs per filing.

Keeps the backend light (no scikit-learn, no raw filings): features, percentiles of
each year-over-year change relative to the dataset, and the terms whose TF-IDF weight
rose or fell most versus the prior year. Percentiles are descriptive only and are not
used for modelling, so there is no leakage concern.
"""
import json
import logging
from pathlib import Path
from typing import List

import joblib
import numpy as np
import pandas as pd

from src.common.config import load_params, setup_logging
from src.common.records import load_records
from src.features.build_features import pair_prior_filings
from src.features.columns import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

FEATURES = Path("data/features/features.csv")
VECTORIZER = Path("data/features/tfidf_vectorizer.joblib")
OUT = Path("data/serving/filings.json")
PERCENTILE_COLUMNS = ["risk_words_change", "tfidf_similarity", "d_neg_ratio", "d_unc_ratio",
                      "d_lit_ratio", "d_fk_grade"]
TOP_TERMS = 8


def percentile_table(features: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    """Percentile rank (0-100) of each value among filings that have a prior year."""
    scored = features[features["has_prior"].astype(bool)]
    return scored[columns].rank(pct=True) * 100.0


def top_term_changes(cur: np.ndarray, prior: np.ndarray, names: np.ndarray, k: int = TOP_TERMS):
    """Terms whose weight rose most (new emphasis) and fell most (dropped) vs last year."""
    diff = cur - prior
    up = [names[i] for i in np.argsort(diff)[::-1][:k] if diff[i] > 0]
    down = [names[i] for i in np.argsort(diff)[:k] if diff[i] < 0]
    return up, down


def _clean(value):
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else value


def main() -> None:
    setup_logging("serving_data")
    params = load_params()
    fcfg = params["features"]

    feats = pd.read_csv(FEATURES, parse_dates=["filing_date"])
    vec = joblib.load(VECTORIZER)
    records = load_records()
    paired = pair_prior_filings(records[["ticker", "accession", "filing_date"]],
                                fcfg["min_prior_gap_days"], fcfg["max_prior_gap_days"])
    prior_of = dict(zip(paired["accession"], paired["prior_accession"]))
    texts = dict(zip(records["accession"], records["risk_factors"]))
    names = vec.get_feature_names_out()

    pct = percentile_table(feats, PERCENTILE_COLUMNS)
    out = []
    for idx, row in feats.iterrows():
        acc = row["accession"]
        prior = prior_of.get(acc)
        prior = prior if isinstance(prior, str) else None
        entry = {
            "ticker": row["ticker"], "accession": acc,
            "filing_date": row["filing_date"].date().isoformat(), "report_date": row["report_date"],
            "has_prior": bool(row["has_prior"]), "prior_accession": prior,
            "features": {c: _clean(float(row[c])) for c in FEATURE_COLUMNS},
            "percentiles": ({c: _clean(float(pct.loc[idx, c])) for c in PERCENTILE_COLUMNS}
                            if idx in pct.index else {}),
            "new_terms": [], "dropped_terms": [],
        }
        if prior and prior in texts and acc in texts:
            m = vec.transform([texts[acc], texts[prior]]).toarray()
            entry["new_terms"], entry["dropped_terms"] = top_term_changes(m[0], m[1], names)
        out.append(entry)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "feature_columns": FEATURE_COLUMNS, "filings": out}
    OUT.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    logger.info("Wrote %d filings to %s", len(out), OUT)


if __name__ == "__main__":
    main()
