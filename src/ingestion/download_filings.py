"""DVC stage `download`: fetch 10-K primary documents from EDGAR.

Idempotent: files already on disk are skipped, so a re-run after a crash
continues where it stopped. Every filing gets a row in data/raw/manifest.csv,
including failures, so nothing disappears silently.
"""
import csv
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List

from src.common.config import load_params, setup_logging
from src.ingestion.edgar_client import (
    EdgarClient,
    EdgarError,
    get_user_agent,
    select_filings,
)

logger = logging.getLogger(__name__)

RAW_DIR = Path("data/raw")
MANIFEST = RAW_DIR / "manifest.csv"
METRICS = Path("reports/download_metrics.json")
FIELDS = [
    "ticker", "cik", "accession", "form", "filing_date", "report_date",
    "primary_document", "path", "status", "error",
]


def read_tickers(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as fh:
        lines = [ln.strip().upper() for ln in fh]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def write_atomic(path: Path, content: bytes) -> None:
    """Write via a temp file so an interrupted run never leaves a partial file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)


def main() -> None:
    setup_logging("download")
    params = load_params()
    client = EdgarClient(
        get_user_agent(),
        min_interval=params["edgar"]["min_interval_seconds"],
        timeout=params["edgar"]["timeout_seconds"],
    )
    cfg = params["data"]
    tickers = read_tickers(cfg["tickers_file"])
    logger.info("Universe: %d tickers", len(tickers))

    ticker_map = client.get_ticker_map()
    rows: List[Dict[str, str]] = []
    started = time.time()

    for ticker in tickers:
        cik = ticker_map.get(ticker)
        if cik is None:
            logger.error("%s: not found in SEC ticker map", ticker)
            rows.append({"ticker": ticker, "status": "failed", "error": "unknown ticker"})
            continue
        try:
            subs = client.get_submissions(cik)
            filings = select_filings(
                subs, ticker, cik, cfg["form_type"], cfg["start_date"], cfg["end_date"]
            )
        except EdgarError as exc:
            logger.error("%s: submissions lookup failed: %s", ticker, exc)
            rows.append({"ticker": ticker, "cik": cik, "status": "failed", "error": str(exc)})
            continue
        logger.info("%s: %d filing(s) in window", ticker, len(filings))

        for f in filings:
            path = RAW_DIR / ticker / f"{f.accession}.htm"
            row = {
                "ticker": ticker, "cik": cik, "accession": f.accession, "form": f.form,
                "filing_date": f.filing_date, "report_date": f.report_date,
                "primary_document": f.primary_document, "path": str(path),
                "status": "", "error": "",
            }
            if path.exists():
                row["status"] = "skipped_existing"
            else:
                try:
                    write_atomic(path, client.download_document(f))
                    row["status"] = "downloaded"
                    logger.info("%s %s downloaded", ticker, f.accession)
                except (EdgarError, OSError) as exc:
                    row["status"], row["error"] = "failed", str(exc)
                    logger.error("%s %s failed: %s", ticker, f.accession, exc)
            rows.append(row)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    ok = sum(r["status"] in ("downloaded", "skipped_existing") for r in rows)
    metrics = {
        "tickers": len(tickers),
        "filings_total": len(rows),
        "filings_ok": ok,
        "filings_failed": len(rows) - ok,
        "elapsed_seconds": round(time.time() - started, 1),
    }
    METRICS.parent.mkdir(parents=True, exist_ok=True)
    METRICS.write_text(json.dumps(metrics, indent=2))
    logger.info("Done: %s", metrics)


if __name__ == "__main__":
    main()
