"""Backend configuration. Every value can be overridden by an environment variable,
so the frontend, backend and model server stay decoupled and re-pointable."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    model_server_url: str = "http://model-server:5001"
    model_timeout_seconds: float = 5.0
    serving_data_path: str = "data/serving/filings.json"
    model_info_path: str = "models/champion_info.json"
    reports_dir: str = "reports"
    elevated_threshold: float = 0.60  # score >= this  -> "Elevated"
    low_threshold: float = 0.40  # score <= this  -> "Lower"

    @classmethod
    def from_env(cls) -> "Settings":
        d = cls()
        return cls(
            model_server_url=os.environ.get("MODEL_SERVER_URL", d.model_server_url).rstrip("/"),
            model_timeout_seconds=float(os.environ.get("MODEL_TIMEOUT_SECONDS", d.model_timeout_seconds)),
            serving_data_path=os.environ.get("SERVING_DATA_PATH", d.serving_data_path),
            model_info_path=os.environ.get("MODEL_INFO_PATH", d.model_info_path),
            reports_dir=os.environ.get("REPORTS_DIR", d.reports_dir),
            elevated_threshold=float(os.environ.get("ELEVATED_THRESHOLD", d.elevated_threshold)),
            low_threshold=float(os.environ.get("LOW_THRESHOLD", d.low_threshold)),
        )


DISCLAIMER = (
    "FilingLens is decision support, not financial advice. The risk score comes from a "
    "model whose accuracy on held-out data could not be distinguished from chance, so "
    "treat it as one input among many. The 'what stands out' section is a factual "
    "comparison of the filing with last year's."
)
