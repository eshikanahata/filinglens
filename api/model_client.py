"""Client for the MLflow model server (the only thing the backend knows about the model)."""

import logging
from typing import List, Optional, Sequence

import requests

logger = logging.getLogger("filinglens.api.model")


class ModelServerError(Exception):
    """The model server is unreachable or returned something unusable."""


class ModelServerClient:
    def __init__(self, base_url: str, timeout: float = 5.0, session: Optional[requests.Session] = None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    def ping(self) -> bool:
        try:
            return self.session.get(f"{self.base_url}/ping", timeout=self.timeout).status_code == 200
        except requests.RequestException:
            return False

    def predict_proba(self, columns: Sequence[str], rows: Sequence[Sequence[Optional[float]]]) -> List[float]:
        """Return P(underperform) for each row. Expects the model to serve predict_proba."""
        payload = {"dataframe_split": {"columns": list(columns), "data": [list(r) for r in rows]}}
        try:
            resp = self.session.post(f"{self.base_url}/invocations", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            preds = resp.json()["predictions"]
        except (requests.RequestException, KeyError, ValueError) as exc:
            logger.error("model server call failed: %s", exc)
            raise ModelServerError(str(exc)) from exc
        try:
            probs = [float(p[1]) for p in preds]
        except (TypeError, IndexError, ValueError) as exc:
            raise ModelServerError("model server returned class labels, expected class probabilities") from exc
        if len(probs) != len(rows):  # never pair scores with the wrong filings
            raise ModelServerError(f"expected {len(rows)} predictions, got {len(probs)}")
        return probs
