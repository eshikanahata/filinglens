"""A small, polite client for SEC EDGAR.

SEC rules this client respects:
  * every request carries a User-Agent with a real contact;
  * at most 10 requests/second (we default to 5);
  * transient failures (429/5xx) are retried with backoff.
"""
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class EdgarError(Exception):
    """Any failure talking to EDGAR."""


class MissingUserAgentError(EdgarError):
    """EDGAR_USER_AGENT is not set to a real contact."""


def get_user_agent() -> str:
    """Read the User-Agent from the environment and reject placeholders."""
    ua = os.environ.get("EDGAR_USER_AGENT", "").strip().strip('"')
    if not ua or "@" not in ua or "example.com" in ua or "your.real.email" in ua:
        raise MissingUserAgentError(
            "Set EDGAR_USER_AGENT to 'Your Name your.email@domain' (SEC requires a "
            "real contact). See .env.example."
        )
    return ua


class RateLimiter:
    """Thread-safe minimum spacing between requests."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval:
                time.sleep(self.min_interval - delta)
            self._last = time.monotonic()


@dataclass(frozen=True)
class FilingRef:
    """Pointer to one filing's primary document."""

    ticker: str
    cik: int
    accession: str          # with dashes, e.g. 0000320193-23-000106
    form: str
    filing_date: str        # ISO yyyy-mm-dd
    report_date: str        # fiscal period end
    primary_document: str

    @property
    def url(self) -> str:
        return ARCHIVE_URL.format(
            cik=self.cik,
            accession=self.accession.replace("-", ""),
            document=self.primary_document,
        )


def select_filings(
    submissions: dict,
    ticker: str,
    cik: int,
    form_type: str = "10-K",
    start_date: str = "2021-01-01",
    end_date: Optional[str] = None,
) -> List[FilingRef]:
    """Pick matching filings out of an EDGAR submissions JSON (pure function).

    Only exact form matches are kept, so 10-K/A and 10-KT are excluded.
    """
    recent = submissions.get("filings", {}).get("recent", {})
    keys = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    columns = [recent.get(k, []) for k in keys]
    out: List[FilingRef] = []
    for acc, fdate, rdate, form, doc in zip(*columns):
        if form != form_type or not doc:
            continue
        if fdate < start_date or (end_date and fdate > end_date):
            continue
        out.append(FilingRef(ticker, cik, acc, form, fdate, rdate, doc))

    older = submissions.get("filings", {}).get("files", [])
    dates = recent.get("filingDate", [])
    if older and dates and min(dates) > start_date:
        logger.warning(
            "%s: window starts %s but 'recent' only reaches back to %s; older "
            "filings are not fetched", ticker, start_date, min(dates),
        )
    return sorted(out, key=lambda f: f.filing_date)


class EdgarClient:
    def __init__(self, user_agent: str, min_interval: float = 0.2, timeout: int = 30):
        self.timeout = timeout
        self.limiter = RateLimiter(min_interval)
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        retry = Retry(
            total=5,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _get(self, url: str) -> requests.Response:
        self.limiter.wait()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            raise EdgarError(f"GET {url} failed: {exc}") from exc

    def get_ticker_map(self) -> Dict[str, int]:
        """Ticker (upper case) -> CIK."""
        data = self._get(TICKER_MAP_URL).json()
        return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}

    def get_submissions(self, cik: int) -> dict:
        return self._get(SUBMISSIONS_URL.format(cik=cik)).json()

    def download_document(self, filing: FilingRef) -> bytes:
        return self._get(filing.url).content
