"""DVC stage `features`: parsed filings -> one feature row per filing.

Leakage control: the TF-IDF vocabulary/IDF weights are fitted ONLY on filings
from the training period (filing_date <= test_start - embargo). Test-period text
never influences the representation.
"""

import json
import logging
from pathlib import Path
from typing import Dict

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from src.common.config import load_params, setup_logging
from src.common.records import load_records
from src.features.columns import FEATURE_COLUMNS
from src.features.text_metrics import (
    lm_ratios,
    load_lm_dictionary,
    readability,
    tokenize,
)

logger = logging.getLogger(__name__)

OUT_DIR = Path("data/features")
METRICS = Path("reports/features_metrics.json")


def pair_prior_filings(df: pd.DataFrame, min_gap: int, max_gap: int) -> pd.DataFrame:
    """Attach each filing's prior-year accession (None if no filing ~1 year earlier)."""
    df = df.sort_values(["ticker", "filing_date"]).reset_index(drop=True)
    prev_acc = df.groupby("ticker")["accession"].shift(1)
    prev_date = df.groupby("ticker")["filing_date"].shift(1)
    gap = (df["filing_date"] - prev_date).dt.days
    ok = gap.between(min_gap, max_gap)
    df["prior_accession"] = prev_acc.where(ok)
    df["prior_gap_days"] = gap
    return df


def base_features(text: str, risk_words: int, full_words: int, lm) -> Dict[str, float]:
    tokens = tokenize(text)
    feats = lm_ratios(tokens, lm)
    feats.update(readability(text, tokens))
    feats["log_risk_words"] = float(np.log1p(risk_words))
    feats["risk_share"] = risk_words / full_words if full_words else np.nan
    return feats


def main() -> None:
    setup_logging("features")
    params = load_params()
    fcfg, split = params["features"], params["split"]

    lm = load_lm_dictionary(fcfg["lm_dictionary_path"])
    df = load_records()
    if df.empty:
        raise RuntimeError("no parsed filings found in data/parsed; run the parse stage first")
    df = pair_prior_filings(df, fcfg["min_prior_gap_days"], fcfg["max_prior_gap_days"])
    logger.info("%d filings, %d with a prior-year filing", len(df), df["prior_accession"].notna().sum())

    train_end = pd.Timestamp(split["test_start_date"]) - pd.Timedelta(days=split["embargo_days"])
    tcfg = fcfg["tfidf"]
    vec = TfidfVectorizer(
        stop_words="english",
        sublinear_tf=True,
        lowercase=True,
        max_features=tcfg["max_features"],
        min_df=tcfg["min_df"],
        ngram_range=tuple(tcfg["ngram_range"]),
    )
    fit_texts = df.loc[df["filing_date"] <= train_end, "risk_factors"]
    vec.fit(fit_texts)
    logger.info(
        "TF-IDF fitted on %d training-period filings (<= %s), vocab %d",
        len(fit_texts),
        train_end.date(),
        len(vec.vocabulary_),
    )
    X = vec.transform(df["risk_factors"])  # rows are L2-normalised
    row_of = {acc: i for i, acc in enumerate(df["accession"])}

    base = {
        r.accession: base_features(r.risk_factors, r.risk_words, r.full_words, lm) for r in df.itertuples(index=False)
    }

    rows = []
    for i, r in enumerate(df.itertuples(index=False)):
        cur = base[r.accession]
        feats = dict(cur)
        prior = r.prior_accession
        if isinstance(prior, str) and prior in base:
            old = base[prior]
            prior_words = df.loc[row_of[prior], "risk_words"]
            feats["risk_words_change"] = (r.risk_words - prior_words) / prior_words if prior_words else np.nan
            feats["tfidf_similarity"] = float(X[i].multiply(X[row_of[prior]]).sum())
            for k in ("neg_ratio", "unc_ratio", "lit_ratio", "fk_grade"):
                feats[f"d_{k}"] = cur[k] - old[k]
            has_prior = True
        else:
            has_prior = False
        rows.append(
            {
                "ticker": r.ticker,
                "accession": r.accession,
                "filing_date": r.filing_date.date().isoformat(),
                "report_date": r.report_date,
                "has_prior": has_prior,
                **feats,
            }
        )

    out = pd.DataFrame(rows)
    for col in FEATURE_COLUMNS:
        if col not in out.columns:
            out[col] = np.nan
    out = out[["ticker", "accession", "filing_date", "report_date", "has_prior"] + FEATURE_COLUMNS]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_DIR / "features.csv", index=False)
    joblib.dump(vec, OUT_DIR / "tfidf_vectorizer.joblib")
    metrics = {
        "filings": int(len(out)),
        "with_prior": int(out["has_prior"].sum()),
        "tfidf_fit_filings": int(len(fit_texts)),
        "tfidf_vocab": len(vec.vocabulary_),
        "train_end": str(train_end.date()),
    }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(metrics, indent=2))
    logger.info("Done: %s", metrics)


if __name__ == "__main__":
    main()
