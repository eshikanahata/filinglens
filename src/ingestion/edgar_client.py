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
from typing import Dict, List, Optional, Sequence
from pathlib import Path
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
# Older filings live in extra pages listed under filings.files (recent holds only ~1,000 entries)
SUBMISSIONS_PAGE_URL = "https://data.sec.gov/submissions/{name}"
_KEYS = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"


class EdgarError(Exception):
    """Any failure talking to EDGAR."""


class MissingUserAgentError(EdgarError):
    """EDGAR_USER_AGENT is not set to a real contact."""


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env reader; real environment variables take precedence."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_user_agent() -> str:
    """Read the User-Agent from the environment (or .env) and reject placeholders."""
    _load_dotenv()
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
    older_pages: Sequence[dict] = (),
) -> List[FilingRef]:
    """Pick matching filings out of EDGAR submissions JSON (pure function).

    Reads the `recent` block plus any older pages (same columns, at top level).
    Only exact form matches are kept, so 10-K/A and 10-KT are excluded.
    Duplicate accession numbers across blocks are kept once.
    """
    blocks = [submissions.get("filings", {}).get("recent", {}), *older_pages]
    seen = set()
    out: List[FilingRef] = []
    for block in blocks:
        for acc, fdate, rdate, form, doc in zip(*[block.get(k, []) for k in _KEYS]):
            if acc in seen or form != form_type or not doc:
                continue
            if fdate < start_date or (end_date and fdate > end_date):
                continue
            seen.add(acc)
            out.append(FilingRef(ticker, cik, acc, form, fdate, rdate, doc))
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

    def _get_json(self, url: str) -> dict:
        """GET and decode JSON; a malformed body becomes an EdgarError, not a crash."""
        try:
            return self._get(url).json()
        except ValueError as exc:
            raise EdgarError(f"GET {url} returned invalid JSON: {exc}") from exc

    def get_older_pages(self, submissions: dict, start_date: str) -> List[dict]:
        """Fetch the extra submissions pages whose date range overlaps the window."""
        pages = []
        for f in submissions.get("filings", {}).get("files", []):
            if f.get("filingTo", "9999-12-31") >= start_date:
                pages.append(self._get_json(SUBMISSIONS_PAGE_URL.format(name=f["name"])))
        return pages

    def get_ticker_map(self) -> Dict[str, int]:
        """Ticker (upper case) -> CIK."""
        data = self._get_json(TICKER_MAP_URL)
        return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}

    def get_submissions(self, cik: int) -> dict:
        return self._get_json(SUBMISSIONS_URL.format(cik=cik))

    def download_document(self, filing: FilingRef) -> bytes:
        return self._get(filing.url).content
