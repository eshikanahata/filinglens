"""Load parsed filing records (output of the `parse` stage)."""

import json
from pathlib import Path

import pandas as pd

COLUMNS = ["ticker", "accession", "filing_date", "report_date", "risk_factors", "risk_words", "full_words"]


def load_records(parsed_dir: str = "data/parsed") -> pd.DataFrame:
    """One row per parsed filing, including the Risk Factors text."""
    rows = []
    for path in sorted(Path(parsed_dir).glob("*/*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        rows.append({k: rec[k] for k in COLUMNS})
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    return df
