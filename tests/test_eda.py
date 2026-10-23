"""EDA stage: the checks that flag data problems, and the report end to end on synthetic data."""

import numpy as np
import pandas as pd

from src.analysis import eda
from src.features.columns import FEATURE_COLUMNS


def test_count_gaps_only_inside_a_companys_run():
    table = pd.DataFrame([[0, 1, 0, 1, 0], [1, 1, 1, 1, 1], [0, 0, 0, 1, 1]])
    assert eda.count_gaps(table) == 1  # leading/trailing zeros are not gaps


def test_iqr_outlier_share():
    values = pd.Series([1.0] * 9 + [100.0])
    assert eda.iqr_outlier_share(values) == 0.1
    assert eda.iqr_outlier_share(pd.Series([], dtype=float)) == 0.0


def test_label_correlations_find_planted_signal_and_report_noise_band():
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame(rng.normal(size=(n, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    df["target"] = (df["unc_ratio"] + rng.normal(scale=0.5, size=n) > 0).astype(int)
    lc = eda.label_correlations(df)
    assert lc.index[0] == "unc_ratio"
    assert abs(lc.attrs["noise_band"] - 1.96 / np.sqrt(n)) < 1e-12


def test_build_report_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(eda, "OUT_DIR", tmp_path / "eda")
    rng = np.random.default_rng(1)
    rows, feats, labels = [], [], []
    for t in ["AAA", "BBB", "CCC"]:
        for k, year in enumerate(range(2021, 2027)):
            if t == "CCC" and year < 2025:
                continue  # a company with few filings, as the download bug produced
            acc = f"{t}-{year}"
            date = f"{year}-02-15"
            rows.append(
                {
                    "ticker": t,
                    "accession": acc,
                    "filing_date": pd.Timestamp(date),
                    "report_date": pd.Timestamp(f"{year - 1}-12-31"),
                    "risk_words": 5000 + k,
                    "full_words": 40000,
                }
            )
            f = {c: rng.normal() for c in FEATURE_COLUMNS}
            f.update(ticker=t, accession=acc, filing_date=date, has_prior=k > 0)
            feats.append(f)
            labels.append(
                {
                    "accession": acc,
                    "filing_date": date,
                    "labeled": True,
                    "target": int(rng.random() > 0.5),
                    "abnormal_ret": rng.normal(scale=0.05),
                }
            )
    parsed = pd.DataFrame(rows)
    manifest = pd.DataFrame({"status": ["downloaded"] * len(parsed)})
    metrics = eda.build_report(
        manifest,
        parsed,
        pd.DataFrame(labels),
        pd.DataFrame(feats),
        pd.DataFrame(columns=["ticker"]),
        {"test_start_date": "2025-07-01", "embargo_days": 45},
    )
    assert metrics["filings"] == len(parsed) and metrics["companies"] == 3
    assert metrics["companies_with_few_filings"] == 1  # CCC
    report = (tmp_path / "eda" / "eda.md").read_text()
    assert "CCC (2)" in report and "## 1. Key findings" in report
    assert len(list((tmp_path / "eda").glob("*.png"))) == 6
