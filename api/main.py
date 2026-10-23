"""FilingLens backend API (FastAPI).

Loosely coupled by design: the only things this service knows about the model are a
configurable URL and the predict_proba contract. It never imports training code.
Start with:  uvicorn api.main:create_app --factory
"""

import logging
import time
from pathlib import Path as FsPath
from typing import Optional

from fastapi import FastAPI, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api import explain, pipeline_status
from api.config import DISCLAIMER, Settings
from api.data_store import DataStore
from api.metrics import Metrics
from api.model_client import ModelServerClient, ModelServerError
from api.pipeline_status import read_json
from api.schemas import (
    AnalysisResponse,
    Changes,
    ErrorResponse,
    FilingRef,
    HealthResponse,
    HistoryPoint,
    HistoryResponse,
    ModelInfo,
    PipelineResponse,
    Signal,
    TickerItem,
    TickersResponse,
)

logger = logging.getLogger("filinglens.api")
TICKER_PATTERN = r"^[A-Za-z][A-Za-z.\-]{0,9}$"
ERRORS = {code: {"model": ErrorResponse} for code in (400, 404, 503)}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def _filing_ref(f: Optional[dict]) -> Optional[FilingRef]:
    return (
        FilingRef(accession=f["accession"], filing_date=f["filing_date"], report_date=f.get("report_date"))
        if f
        else None
    )


def _row(f: dict, columns) -> list:
    return [f["features"].get(c) for c in columns]


def create_app(settings: Optional[Settings] = None, model_client: Optional[ModelServerClient] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    store = DataStore(settings.serving_data_path)
    model = model_client or ModelServerClient(settings.model_server_url, settings.model_timeout_seconds)
    metrics = Metrics(settings.reports_dir, settings.model_info_path)

    app = FastAPI(
        title="FilingLens API",
        version="1.0.0",
        description="Risk-signal analysis of SEC 10-K filings. Decision support only.",
    )

    def model_info() -> Optional[ModelInfo]:
        raw = read_json(FsPath(settings.model_info_path))
        if not raw:
            return None
        return ModelInfo(
            name=str(raw.get("champion_model", "unknown")),
            version=str(raw.get("version", "?")),
            run_id=str(raw.get("run_id", "")),
            test_roc_auc=raw.get("test_roc_auc"),
            cv_roc_auc=raw.get("cv_roc_auc"),
        )

    def score_rows(rows: list) -> list:
        started = time.perf_counter()
        try:
            scores = model.predict_proba(store.feature_columns, rows)
        except ModelServerError as exc:
            metrics.model_calls.labels("error").inc()
            raise ApiError(
                503, "model_unavailable", "The scoring service is temporarily unavailable. Please try again shortly."
            ) from exc
        metrics.model_calls.labels("success").inc()
        metrics.model_latency.observe(time.perf_counter() - started)
        return scores

    def label(score: Optional[float]) -> str:
        return explain.signal_label(score, settings.elevated_threshold, settings.low_threshold)

    # ---------- middleware and error handlers ----------
    @app.middleware("http")
    async def instrument(request: Request, call_next):
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started
            route = request.scope.get("route")
            endpoint = route.path if route else "unmatched"
            metrics.requests.labels(request.method, endpoint, str(status)).inc()
            metrics.latency.labels(endpoint).observe(elapsed)
            logger.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, status, elapsed * 1000)

    def error_response(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})

    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        return error_response(
            400, "invalid_input", "Please enter a valid ticker symbol: letters only, for example AAPL."
        )

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, exc: Exception):
        logger.exception("unhandled error: %s", exc)
        return error_response(500, "internal_error", "Something went wrong on our side. Please try again.")

    def require_ticker(ticker: str) -> str:
        t = ticker.upper()
        if not store.has(t):
            raise ApiError(
                404, "unknown_ticker", f"We don't have data for '{t}'. Pick a company from the supported list."
            )
        return t

    # ---------- endpoints ----------
    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        up = model.ping()
        return HealthResponse(
            status="ok" if up else "degraded",
            model_server="up" if up else "down",
            filings_loaded=store.n_filings,
            companies=len(store.tickers()),
        )

    @app.get("/tickers", response_model=TickersResponse, tags=["analysis"])
    def tickers():
        items = [
            TickerItem(ticker=t, n_filings=len(store.filings(t)), latest_filing_date=store.latest(t)["filing_date"])
            for t in store.tickers()
        ]
        return TickersResponse(tickers=items)

    @app.get("/analysis/{ticker}", response_model=AnalysisResponse, responses=ERRORS, tags=["analysis"])
    def analysis(ticker: str = Path(..., pattern=TICKER_PATTERN)):
        t = require_ticker(ticker)
        f = store.latest(t)
        prev = store.previous(f)
        score = None
        if f["has_prior"]:
            score = score_rows([_row(f, store.feature_columns)])[0]
            metrics.score.observe(score)
        lbl = label(score)
        metrics.analyses.labels(lbl).inc()
        feats, pcts = f["features"], f.get("percentiles", {})
        if f["has_prior"]:
            reasons = explain.build_reasons(feats, pcts)
        else:
            reasons = [
                "This is the earliest filing we have for this company, so there is no " "prior year to compare against."
            ]
        changes = Changes(
            risk_section_change_pct=feats.get("risk_words_change"),
            text_similarity=feats.get("tfidf_similarity"),
            negative_tone_change=feats.get("d_neg_ratio"),
            uncertainty_change=feats.get("d_unc_ratio"),
            litigious_change=feats.get("d_lit_ratio"),
            readability_grade_change=feats.get("d_fk_grade"),
            new_terms=f.get("new_terms", []),
            dropped_terms=f.get("dropped_terms", []),
        )
        return AnalysisResponse(
            ticker=t,
            filing=_filing_ref(f),
            previous_filing=_filing_ref(prev),
            signal=Signal(
                label=lbl,
                score=score,
                elevated_threshold=settings.elevated_threshold,
                low_threshold=settings.low_threshold,
            ),
            reasons=reasons,
            changes=changes,
            model=model_info(),
            disclaimer=DISCLAIMER,
        )

    @app.get("/analysis/{ticker}/history", response_model=HistoryResponse, responses=ERRORS, tags=["analysis"])
    def history(ticker: str = Path(..., pattern=TICKER_PATTERN)):
        t = require_ticker(ticker)
        filings = store.filings(t)
        scorable = [f for f in filings if f["has_prior"]]
        scores = dict(
            zip(
                (f["accession"] for f in scorable),
                score_rows([_row(f, store.feature_columns) for f in scorable]) if scorable else [],
            )
        )
        points = [
            HistoryPoint(
                accession=f["accession"],
                filing_date=f["filing_date"],
                score=scores.get(f["accession"]),
                label=label(scores.get(f["accession"])),
                text_similarity=f["features"].get("tfidf_similarity"),
            )
            for f in filings
        ]
        return HistoryResponse(ticker=t, points=points)

    @app.get("/pipeline/runs", response_model=PipelineResponse, tags=["pipeline"])
    def pipeline():
        data = pipeline_status.collect(settings.reports_dir)
        return PipelineResponse(**data, champion=model_info())

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics():
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    return app
