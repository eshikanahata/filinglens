"""DVC stage `labels`: abnormal return after each filing -> binary target.

Definition (no look-ahead into the features):
  base price  = close on the last trading day ON OR BEFORE the filing date
  end price   = close `horizon` trading days after that day
  abnormal    = stock return - benchmark return over the same dates
  target      = 1 if abnormal < 0 (underperformed), else 0
Filings without `horizon` trading days of data yet stay unlabeled; they are the
"latest filing" the application shows, never training data.
"""

import json
import logging
from pathlib import Path
from typing import Dict

import pandas as pd

from src.common.config import load_params, setup_logging
from src.common.records import load_records

logger = logging.getLogger(__name__)

PRICES = Path("data/prices/prices.csv")
OUT = Path("data/labels/labels.csv")
METRICS = Path("reports/labels_metrics.json")
MAX_GAP_DAYS = 7  # filing date must be within a week of a trading day in the data


def _unlabeled(reason: str) -> Dict:
    return {
        "labeled": False,
        "base_date": "",
        "end_date": "",
        "stock_ret": None,
        "bench_ret": None,
        "abnormal_ret": None,
        "target": None,
        "reason": reason,
    }


def compute_label(stock: pd.Series, bench: pd.Series, filing_date: str, horizon: int) -> Dict:
    """Pure function: label one filing from stock and benchmark close series."""
    px = pd.concat({"s": stock, "b": bench}, axis=1).dropna().sort_index()
    fdate = pd.Timestamp(filing_date)
    pos = px.index.searchsorted(fdate, side="right") - 1
    if pos < 0:
        return _unlabeled("no price on or before filing date")
    if (fdate - px.index[pos]).days > MAX_GAP_DAYS:
        return _unlabeled("price data gap around filing date")
    end_pos = pos + horizon
    if end_pos >= len(px):
        return _unlabeled(f"fewer than {horizon} trading days after filing")

    s_ret = px["s"].iloc[end_pos] / px["s"].iloc[pos] - 1
    b_ret = px["b"].iloc[end_pos] / px["b"].iloc[pos] - 1
    abnormal = s_ret - b_ret
    return {
        "labeled": True,
        "base_date": str(px.index[pos].date()),
        "end_date": str(px.index[end_pos].date()),
        "stock_ret": float(s_ret),
        "bench_ret": float(b_ret),
        "abnormal_ret": float(abnormal),
        "target": int(abnormal < 0),
        "reason": "",
    }


def main() -> None:
    setup_logging("labels")
    params = load_params()
    horizon = params["labels"]["horizon_trading_days"]
    bench = params["prices"]["benchmark"]

    prices = pd.read_csv(PRICES, index_col="date", parse_dates=True)
    records = load_records().drop(columns=["risk_factors"])
    rows = []
    for rec in records.itertuples(index=False):
        base = {
            "ticker": rec.ticker,
            "accession": rec.accession,
            "filing_date": rec.filing_date.date().isoformat(),
            "report_date": rec.report_date,
        }
        if rec.ticker not in prices.columns:
            rows.append({**base, **_unlabeled("no prices for ticker")})
            continue
        rows.append({**base, **compute_label(prices[rec.ticker], prices[bench], base["filing_date"], horizon)})

    labels = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    labels.to_csv(OUT, index=False)

    labeled = labels[labels["labeled"]]
    metrics = {
        "filings_total": int(len(labels)),
        "filings_labeled": int(len(labeled)),
        "filings_unlabeled": int(len(labels) - len(labeled)),
        "positive_rate": round(float(labeled["target"].mean()), 4) if len(labeled) else 0.0,
        "horizon_trading_days": horizon,
    }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(metrics, indent=2))
    logger.info("Done: %s", metrics)
    if len(labels) - len(labeled):
        logger.info("Unlabeled reasons:\n%s", labels[~labels["labeled"]]["reason"].value_counts())


if __name__ == "__main__":
    main()
