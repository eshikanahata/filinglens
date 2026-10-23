"""In-memory view of the precomputed serving data (output of the serving_data stage)."""

import json
from pathlib import Path
from typing import Dict, List, Optional


class DataStore:
    def __init__(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Serving data not found at {path}. Run `dvc repro` (stage serving_data) "
                "and mount data/serving into the backend container."
            )
        payload = json.loads(p.read_text(encoding="utf-8"))
        self.feature_columns: List[str] = payload["feature_columns"]
        self._by_accession: Dict[str, dict] = {}
        self._by_ticker: Dict[str, List[dict]] = {}
        for f in payload["filings"]:
            self._by_accession[f["accession"]] = f
            self._by_ticker.setdefault(f["ticker"].upper(), []).append(f)
        for rows in self._by_ticker.values():
            rows.sort(key=lambda r: r["filing_date"])

    @property
    def n_filings(self) -> int:
        return len(self._by_accession)

    def tickers(self) -> List[str]:
        return sorted(self._by_ticker)

    def has(self, ticker: str) -> bool:
        return ticker.upper() in self._by_ticker

    def filings(self, ticker: str) -> List[dict]:
        return self._by_ticker.get(ticker.upper(), [])

    def latest(self, ticker: str) -> Optional[dict]:
        rows = self.filings(ticker)
        return rows[-1] if rows else None

    def previous(self, filing: dict) -> Optional[dict]:
        acc = filing.get("prior_accession")
        return self._by_accession.get(acc) if acc else None
