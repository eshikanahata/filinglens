"""The frontend's only link to the rest of the system: REST calls to the backend API.

Every failure is converted to an ApiError with a message safe to show a non-technical
user (no stack traces, no internal URLs).
"""
import os
from typing import Any, Dict

import requests

TIMEOUT_SECONDS = 10


class ApiError(Exception):
    def __init__(self, message: str, status: int = 0, code: str = "error") -> None:
        super().__init__(message)
        self.message, self.status, self.code = message, status, code


def backend_url() -> str:
    return os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")


def _get(path: str) -> Dict[str, Any]:
    try:
        resp = requests.get(f"{backend_url()}{path}", timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiError("We can't reach the analysis service right now. "
                       "Please try again in a moment.", code="unreachable") from exc
    if resp.status_code >= 400:
        try:
            err = resp.json()["error"]
            raise ApiError(err["message"], resp.status_code, err["code"])
        except (ValueError, KeyError, TypeError):
            raise ApiError("The service returned an unexpected response. Please try again.",
                           resp.status_code) from None
    try:
        return resp.json()
    except ValueError as exc:
        raise ApiError("The service returned an unreadable response. Please try again.") from exc


def get_tickers() -> Dict[str, Any]:
    return _get("/tickers")


def get_analysis(ticker: str) -> Dict[str, Any]:
    return _get(f"/analysis/{ticker}")


def get_history(ticker: str) -> Dict[str, Any]:
    return _get(f"/analysis/{ticker}/history")


def get_pipeline() -> Dict[str, Any]:
    return _get("/pipeline/runs")
