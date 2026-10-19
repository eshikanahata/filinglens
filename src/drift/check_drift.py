"""DVC stage `drift`: compare the latest filings' features with the training period.

Label-free on purpose: new filings have no label for ~6 weeks, but drift must be visible
immediately. Reference = training-period filings; current = filings from
drift.current_start_date (default: the test start) onward.

`--simulate-shift` deliberately shifts the current batch (demo and acceptance test); the
report is then marked simulated. Rerun `dvc repro drift` to restore the real result.
"""
import argparse
import json
import logging
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

from src.common.config import load_params, setup_logging
from src.common.run_log import log_event
from src.drift.drift import DEFAULT_SHIFT_SD, detect_drift, simulate_shift
from src.features.columns import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

FEATURES = Path("data/features/features.csv")
REPORT = Path("reports/drift_report.json")
METRICS = Path("reports/drift_metrics.json")
MIN_REFERENCE = 30


def select_batches(features: pd.DataFrame, split: Dict, drift_cfg: Dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """(reference, current) among filings that have a prior year."""
    df = features.copy()
    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df = df[df["has_prior"].astype(bool)]
    test_start = pd.Timestamp(split["test_start_date"])
    train_end = test_start - pd.Timedelta(days=split["embargo_days"])
    current_start = pd.Timestamp(drift_cfg.get("current_start_date") or test_start)
    return df[df["filing_date"] <= train_end], df[df["filing_date"] >= current_start]


def run_check(features: pd.DataFrame, params: Dict, simulate: bool = False,
              shift_sd: float = DEFAULT_SHIFT_SD) -> Dict:
    cfg = params["drift"]
    reference, current = select_batches(features, params["split"], cfg)
    if len(reference) < MIN_REFERENCE or len(current) < cfg["min_current_samples"]:
        return {"status": "insufficient_data", "drift_detected": False, "simulated": simulate,
                "n_reference": int(len(reference)), "n_current": int(len(current)),
                "n_features": len(FEATURE_COLUMNS), "n_drifted": 0, "drifted_share": 0.0,
                "max_psi": 0.0, "features": {}, "thresholds": {}}
    if simulate:
        current = simulate_shift(current, reference, FEATURE_COLUMNS, shift_sd)
    report = detect_drift(reference, current, FEATURE_COLUMNS, cfg["psi_threshold"],
                          cfg["ks_alpha"], cfg["min_drifted_share"], cfg["bins"])
    report.update(status="ok", simulated=simulate)
    return report


def write_reports(report: Dict, report_path: Path = REPORT, metrics_path: Path = METRICS) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    metrics_path.write_text(json.dumps({
        "drift_detected": int(report["drift_detected"]), "drifted_features": report["n_drifted"],
        "drifted_share": report["drifted_share"], "max_psi": report["max_psi"],
        "n_reference": report["n_reference"], "n_current": report["n_current"],
        "simulated": int(report["simulated"]),
    }, indent=2))


def main() -> None:
    setup_logging("drift")
    cli = argparse.ArgumentParser()
    cli.add_argument("--simulate-shift", action="store_true",
                     help="deliberately shift the current batch (demo / acceptance test)")
    cli.add_argument("--shift-sd", type=float, default=DEFAULT_SHIFT_SD)
    args = cli.parse_args()

    params = load_params()
    report = run_check(pd.read_csv(FEATURES), params, args.simulate_shift, args.shift_sd)
    write_reports(report)
    status = "drift" if report["drift_detected"] else "ok"
    log_event("drift_check", status, drifted_features=report["n_drifted"],
              max_psi=report["max_psi"], simulated=report["simulated"],
              n_current=report["n_current"])
    logger.info("Drift %s: %d/%d features drifted (max PSI %.3f, simulated=%s)",
                "DETECTED" if report["drift_detected"] else "not detected", report["n_drifted"],
                report["n_features"], report["max_psi"], report["simulated"])


if __name__ == "__main__":
    main()
