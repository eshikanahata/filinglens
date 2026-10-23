"""DVC stage `export_model`: copy the registry's `champion` model into a portable folder.

Why: the MLflow registry stores artifact paths as absolute host paths, which do not exist
inside a Docker container. Exporting once gives the model-server container a
self-contained folder (models/champion) plus a small info file for the backend.
Rollback = move the `champion` alias in the registry, then rerun this stage.
"""

import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Dict

import mlflow
from mlflow.tracking import MlflowClient

from src.common.config import load_params, setup_logging

logger = logging.getLogger(__name__)

DST = Path("models/champion")
INFO = Path("models/champion_info.json")
REPORTS = Path("reports")


def export_champion(tracking_uri: str, name: str, alias: str, dst: Path) -> str:
    """Download the aliased model version into `dst`; return its version string."""
    mlflow.set_tracking_uri(tracking_uri)
    version = MlflowClient().get_model_version_by_alias(name, alias).version
    with tempfile.TemporaryDirectory() as tmp:
        local = mlflow.artifacts.download_artifacts(artifact_uri=f"models:/{name}@{alias}", dst_path=tmp)
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(local, dst)
    return str(version)


def build_info(version: str, alias: str, train_run: Dict, train_metrics: Dict) -> Dict:
    return {
        "registered_model": train_run.get("registered_model"),
        "alias": alias,
        "version": version,
        "champion_model": train_run.get("champion_model"),
        "run_id": train_run.get("champion_run_id"),
        "git_commit": train_run.get("git_commit"),
        "test_roc_auc": train_metrics.get("champion_test_roc_auc"),
        "cv_roc_auc": train_metrics.get("champion_cv_roc_auc"),
    }


def main() -> None:
    setup_logging("export_model")
    cfg = load_params()["mlflow"]
    alias = "champion"
    version = export_champion(cfg["tracking_uri"], cfg["registered_model_name"], alias, DST)
    train_run = json.loads((REPORTS / "train_run.json").read_text())
    train_metrics = json.loads((REPORTS / "train_metrics.json").read_text())
    if str(train_run.get("registered_version")) != version:
        logger.warning(
            "Registry %s points to v%s but last training registered v%s " "(alias was moved, e.g. a rollback)",
            alias,
            version,
            train_run.get("registered_version"),
        )
    INFO.write_text(json.dumps(build_info(version, alias, train_run, train_metrics), indent=2))
    logger.info("Exported %s v%s to %s", cfg["registered_model_name"], version, DST)


if __name__ == "__main__":
    main()
