"""Pydantic request/response models: the API contract documented in the LLD."""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FilingRef(BaseModel):
    accession: str
    filing_date: str
    report_date: Optional[str] = None


class Signal(BaseModel):
    label: str                       # Elevated | Moderate | Lower | Not enough data
    score: Optional[float] = None    # estimated probability of underperforming the market
    elevated_threshold: float
    low_threshold: float


class Changes(BaseModel):
    risk_section_change_pct: Optional[float] = None   # e.g. 0.18 = +18% words vs last year
    text_similarity: Optional[float] = None           # 0..1, TF-IDF cosine vs last year
    negative_tone_change: Optional[float] = None      # change in share of negative words
    uncertainty_change: Optional[float] = None
    litigious_change: Optional[float] = None
    readability_grade_change: Optional[float] = None  # Flesch-Kincaid grade-level change
    new_terms: List[str] = []
    dropped_terms: List[str] = []


class ModelInfo(BaseModel):
    name: str
    version: str
    run_id: str
    test_roc_auc: Optional[float] = None
    cv_roc_auc: Optional[float] = None


class AnalysisResponse(BaseModel):
    ticker: str
    filing: FilingRef
    previous_filing: Optional[FilingRef] = None
    signal: Signal
    reasons: List[str]
    changes: Changes
    model: Optional[ModelInfo] = None
    disclaimer: str


class TickerItem(BaseModel):
    ticker: str
    n_filings: int
    latest_filing_date: str


class TickersResponse(BaseModel):
    tickers: List[TickerItem]


class HistoryPoint(BaseModel):
    accession: str
    filing_date: str
    score: Optional[float] = None
    label: str
    text_similarity: Optional[float] = None


class HistoryResponse(BaseModel):
    ticker: str
    points: List[HistoryPoint]


class StageStatus(BaseModel):
    name: str
    status: str                      # ok | warning | missing
    updated_at: Optional[str] = None
    metrics: Dict[str, Any] = {}


class PipelineResponse(BaseModel):
    stages: List[StageStatus]
    model_comparison: List[Dict[str, Any]] = []
    test_uncertainty: List[Dict[str, Any]] = []
    ray_benchmark: List[Dict[str, Any]] = []
    parse_failure_count: int = 0
    champion: Optional[ModelInfo] = None


class HealthResponse(BaseModel):
    status: str                      # ok | degraded
    model_server: str                # up | down
    filings_loaded: int
    companies: int


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
