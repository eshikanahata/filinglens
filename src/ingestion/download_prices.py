"""DVC stage `prices`: daily adjusted closes for the universe plus a benchmark.

Downloaded once and versioned in DVC, because the free source can be flaky.
The end date comes from params.yaml (not "today") so the stage is reproducible.
"""
import json
import logging
import time
from pathlib import Path
from typing import Dict, List

import pandas as pd

from src.common.config import load_params, setup_logging

logger = logging.getLogger(__name__)

OUT = Path("data/prices/prices.csv")
METRICS = Path("reports/prices_metrics.json")


def read_tickers(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as fh:
        lines = [ln.strip().upper() for ln in fh]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def validate_coverage(close: pd.DataFrame, symbols: List[str], min_rows: int = 500) -> Dict:
    """Report symbols that are missing or have suspiciously little history."""
    missing = [s for s in symbols if s not in close.columns]
    sparse = [s for s in symbols
              if s in close.columns and close[s].notna().sum() < min_rows]
    return {"missing": missing, "sparse": sparse}


def fetch_prices(symbols: List[str], start: str, end: str, retries: int) -> pd.DataFrame:
    """Download adjusted closes with retry and backoff (yfinance)."""
    import yfinance as yf  # imported here so tests do not need the package

    last_error: Exception = RuntimeError("no attempt made")
    for attempt in range(1, retries + 1):
        try:
            raw = yf.download(symbols, start=start, end=end, auto_adjust=True,
                              progress=False, group_by="column", threads=True)
            close = raw["Close"]
            if close.empty:
                raise RuntimeError("empty price frame returned")
            return close
        except Exception as exc:  # noqa: BLE001 - network errors vary widely
            last_error = exc
            wait = 5 * attempt
            logger.warning("Price download attempt %d/%d failed: %s (retry in %ds)",
                           attempt, retries, exc, wait)
            time.sleep(wait)
    raise RuntimeError(f"price download failed after {retries} attempts: {last_error}")


def main() -> None:
    setup_logging("prices")
    params = load_params()
    cfg = params["prices"]
    tickers = read_tickers(params["data"]["tickers_file"])
    bench = cfg["benchmark"]
    symbols = sorted(set(tickers + [bench]))
    logger.info("Downloading %d symbols (%s to %s)", len(symbols), cfg["start_date"], cfg["end_date"])

    close = fetch_prices(symbols, cfg["start_date"], cfg["end_date"], cfg["max_retries"])
    close.index.name = "date"
    close = close.sort_index()

    cov = validate_coverage(close, symbols)
    if bench in cov["missing"] or bench in cov["sparse"]:
        raise RuntimeError(f"benchmark {bench} has no usable prices; cannot build labels")
    if cov["missing"] or cov["sparse"]:
        logger.warning("Missing: %s | Sparse: %s (their filings will be unlabeled)",
                       cov["missing"], cov["sparse"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    close.to_csv(OUT)
    metrics = {
        "symbols_requested": len(symbols),
        "symbols_ok": len(symbols) - len(cov["missing"]) - len(cov["sparse"]),
        "symbols_missing": len(cov["missing"]),
        "symbols_sparse": len(cov["sparse"]),
        "trading_days": int(len(close)),
        "first_date": str(close.index.min().date()),
        "last_date": str(close.index.max().date()),
    }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(metrics, indent=2))
    logger.info("Done: %s", metrics)


if __name__ == "__main__":
    main()
