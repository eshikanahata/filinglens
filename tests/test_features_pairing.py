import pandas as pd

from src.features.build_features import pair_prior_filings


def frame(rows):
    df = pd.DataFrame(rows, columns=["ticker", "accession", "filing_date"])
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df


def test_pairs_consecutive_years_only_within_gap():
    df = frame(
        [
            ("AAA", "a1", "2022-02-01"),
            ("AAA", "a2", "2023-02-05"),  # ~1 year after a1 -> paired
            ("AAA", "a3", "2025-02-01"),  # 2-year gap -> no prior
            ("BBB", "b1", "2023-03-01"),  # first filing -> no prior
        ]
    )
    out = pair_prior_filings(df, 300, 450).set_index("accession")
    assert out.loc["a2", "prior_accession"] == "a1"
    assert pd.isna(out.loc["a3", "prior_accession"])
    assert pd.isna(out.loc["a1", "prior_accession"])
    assert pd.isna(out.loc["b1", "prior_accession"])


def test_pairing_does_not_cross_tickers():
    df = frame([("AAA", "a1", "2022-02-01"), ("BBB", "b1", "2023-02-01")])
    out = pair_prior_filings(df, 300, 450)
    assert out["prior_accession"].isna().all()
