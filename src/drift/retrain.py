"""Drift-triggered retraining with a promotion gate and automatic rollback.

Flow:  drift check -> (drift or --force) -> retrain -> compare with previous champion
       -> promote the new model, or restore the previous one -> re-export for serving.

Every step is appended to reports/run_history.jsonl so the console shows what happened.
The previous model version always stays in the registry, so rollback is just moving the
`champion` alias back.
"""

import argparse
import json
import logging
import math
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from mlflow.tracking import MlflowClient
import mlflow

from src.common.config import load_params, setup_logging
from src.common.run_log import log_event

logger = logging.getLogger(__name__)
DRIFT_METRICS = Path("reports/drift_metrics.json")


def decide_promotion(prev_cv: Optional[float], new_cv: Optional[float], tolerance: float) -> str:
    """'promote' unless the new model is worse than the previous one by more than `tolerance`."""
    if new_cv is None or (isinstance(new_cv, float) and math.isnan(new_cv)):
        return "rollback"
    if prev_cv is None or (isinstance(prev_cv, float) and math.isnan(prev_cv)):
        return "promote"
    return "promote" if new_cv + tolerance >= prev_cv else "rollback"


class DvcRunner:
    def dvc(self, *args: str) -> None:
        logger.info("dvc %s", " ".join(args))
        subprocess.run(["dvc", *args], check=True)

    def python_module(self, module: str, *args: str) -> None:
        logger.info("python -m %s %s", module, " ".join(args))
        subprocess.run([sys.executable, "-m", module, *args], check=True)


class MlflowRegistry:
    def __init__(self, tracking_uri: str, name: str, alias: str = "champion") -> None:
        mlflow.set_tracking_uri(tracking_uri)
        self.client, self.name, self.alias = MlflowClient(), name, alias

    def champion_version(self) -> Optional[str]:
        try:
            return str(self.client.get_model_version_by_alias(self.name, self.alias).version)
        except Exception:  # noqa: BLE001 - no champion yet
            return None

    def latest_version(self) -> str:
        versions = self.client.search_model_versions(f"name='{self.name}'")
        return str(max(int(v.version) for v in versions))

    def cv_auc(self, version: str) -> Optional[float]:
        mv = self.client.get_model_version(self.name, str(version))
        return self.client.get_run(mv.run_id).data.metrics.get("cv_roc_auc")

    def set_champion(self, version: str) -> None:
        self.client.set_registered_model_alias(self.name, self.alias, str(version))


def read_drift_metrics(path: Path = DRIFT_METRICS) -> Dict:
    return json.loads(Path(path).read_text())


def orchestrate(
    runner,
    registry,
    tolerance: float,
    force: bool = False,
    simulate_shift: bool = False,
    read_metrics: Callable[[], Dict] = read_drift_metrics,
    log: Callable[..., Dict] = log_event,
) -> Dict:
    """Run one monitor-and-maybe-retrain cycle. Returns a summary of what happened."""
    if simulate_shift:
        runner.python_module("src.drift.check_drift", "--simulate-shift")
    else:
        runner.dvc("repro", "drift")
    metrics = read_metrics()
    drifted = bool(metrics.get("drift_detected"))
    if not (drifted or force):
        return {"drift_detected": False, "retrained": False}

    reason = "drift" if drifted else "forced"
    previous = registry.champion_version()
    prev_cv = registry.cv_auc(previous) if previous else None
    log("retrain_started", "ok", reason=reason, previous_version=previous)

    runner.dvc("repro", "-f", "-s", "train")
    new_version = registry.latest_version()
    new_cv = registry.cv_auc(new_version)
    decision = decide_promotion(prev_cv, new_cv, tolerance)

    if decision == "rollback" and previous:
        registry.set_champion(previous)
        log(
            "model_rollback",
            "warning",
            rejected_version=new_version,
            restored_version=previous,
            prev_cv_auc=prev_cv,
            new_cv_auc=new_cv,
        )
    else:
        log(
            "model_promoted",
            "ok",
            version=new_version,
            previous_version=previous,
            prev_cv_auc=prev_cv,
            new_cv_auc=new_cv,
        )

    runner.dvc("repro", "-f", "-s", "export_model")
    serving = registry.champion_version()
    log("model_exported", "ok", version=serving)
    return {
        "drift_detected": drifted,
        "retrained": True,
        "reason": reason,
        "decision": decision,
        "previous_version": previous,
        "new_version": new_version,
        "serving_version": serving,
        "prev_cv_auc": prev_cv,
        "new_cv_auc": new_cv,
    }


def main() -> None:
    setup_logging("retrain")
    cli = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    cli.add_argument("--force", action="store_true", help="retrain even without drift")
    cli.add_argument("--simulate-shift", action="store_true", help="demo: shift the current batch first")
    cli.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="override retrain.promotion_tolerance (demo: -1 makes every new model look worse, " "forcing a rollback)",
    )
    args = cli.parse_args()

    params = load_params()
    registry = MlflowRegistry(params["mlflow"]["tracking_uri"], params["mlflow"]["registered_model_name"])
    tolerance = args.tolerance if args.tolerance is not None else params["retrain"]["promotion_tolerance"]
    logger.info("Promotion tolerance in force: %s", tolerance)
    result = orchestrate(DvcRunner(), registry, tolerance, args.force, args.simulate_shift)
    print(json.dumps(result, indent=2))
    if result["retrained"]:
        print("\nNext: docker compose up -d --force-recreate model-server backend")


if __name__ == "__main__":
    main()
