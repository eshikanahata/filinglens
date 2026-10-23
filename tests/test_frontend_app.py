"""Drives the real Streamlit script with a faked backend (no server needed)."""

from pathlib import Path

import pytest
import requests

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")

ANALYSIS = {
    "ticker": "AAA",
    "filing": {"accession": "a3", "filing_date": "2025-02-01", "report_date": "2024-12-31"},
    "previous_filing": {"accession": "a2", "filing_date": "2024-02-01", "report_date": "2023-12-31"},
    "signal": {"label": "Moderate", "score": 0.52, "elevated_threshold": 0.6, "low_threshold": 0.4},
    "reasons": ["The risk-factors section grew 30% compared with last year."],
    "changes": {
        "risk_section_change_pct": 0.3,
        "text_similarity": 0.8,
        "negative_tone_change": 0.001,
        "uncertainty_change": 0.002,
        "litigious_change": 0.0,
        "readability_grade_change": 0.4,
        "new_terms": ["supply chain"],
        "dropped_terms": ["covid"],
    },
    "model": {"name": "xgboost", "version": "3", "run_id": "r", "test_roc_auc": 0.48, "cv_roc_auc": 0.52},
    "disclaimer": "FilingLens is decision support, not financial advice.",
}
PIPELINE = {
    "stages": [
        {
            "name": "parse",
            "status": "ok",
            "updated_at": "2026-10-15T10:00:00+00:00",
            "metrics": {"success_rate": 1.0, "filings_per_minute": 330.0},
        }
    ],
    "model_comparison": [],
    "test_uncertainty": [],
    "ray_benchmark": [],
    "parse_failure_count": 0,
    "champion": {"name": "xgboost", "version": "3", "run_id": "r"},
}


class Resp:
    def __init__(self, status, payload):
        self.status_code, self._p = status, payload

    def json(self):
        return self._p


def fake_get(url, timeout):
    if url.endswith("/tickers"):
        return Resp(200, {"tickers": [{"ticker": "AAA", "n_filings": 3, "latest_filing_date": "2025-02-01"}]})
    if url.endswith("/history"):
        return Resp(
            200,
            {
                "ticker": "AAA",
                "points": [
                    {
                        "accession": "a2",
                        "filing_date": "2024-02-01",
                        "score": 0.4,
                        "label": "Moderate",
                        "text_similarity": 0.8,
                    },
                    {
                        "accession": "a3",
                        "filing_date": "2025-02-01",
                        "score": 0.52,
                        "label": "Moderate",
                        "text_similarity": 0.8,
                    },
                ],
            },
        )
    if "/analysis/" in url:
        return Resp(200, ANALYSIS)
    if url.endswith("/pipeline/runs"):
        return Resp(200, PIPELINE)
    return Resp(404, {"error": {"code": "x", "message": "nope"}})


@pytest.fixture(autouse=True)
def backend(monkeypatch):
    import streamlit as st

    st.cache_data.clear()
    monkeypatch.setattr(requests, "get", fake_get)


def test_analysis_page_shows_signal_and_reasons():
    at = AppTest.from_file(APP, default_timeout=20).run()
    assert not at.exception
    at.selectbox[0].select(at.selectbox[0].options[0]).run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Moderate" in text and "grew 30%" in text
    assert any("decision support" in i.value for i in at.info)


def test_console_page_renders():
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.sidebar.radio[0].set_value("Pipeline console").run()
    assert not at.exception
    assert any("Parse success rate" == m.label for m in at.metric)


def test_backend_down_shows_friendly_error(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(requests, "get", boom)
    at = AppTest.from_file(APP, default_timeout=20).run()
    assert not at.exception
    assert any("can't reach" in e.value for e in at.error)
