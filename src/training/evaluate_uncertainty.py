"""Bootstrap confidence intervals for test-set metrics (reporting only).

Reads reports/test_predictions_<model>.csv written by the train stage. This does
NOT select or tune anything; it only quantifies how uncertain the test numbers are.
Caveat: resampling filings assumes they are independent. Filings from the same
period share market conditions, so these intervals are, if anything, too narrow.
"""
import logging
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

from src.common.config import setup_logging

logger = logging.getLogger(__name__)
REPORTS = Path("reports")


def bootstrap_ci(y_true, proba, n_boot: int = 2000, seed: int = 42,
                 threshold: float = 0.5) -> Dict[str, float]:
    """Point estimates and 95% percentile intervals for AUC and accuracy."""
    y, p = np.asarray(y_true), np.asarray(proba)
    rng = np.random.default_rng(seed)
    aucs, accs = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        if len(np.unique(y[idx])) < 2:
            continue
        aucs.append(roc_auc_score(y[idx], p[idx]))
        accs.append(accuracy_score(y[idx], (p[idx] >= threshold).astype(int)))
    auc_lo, auc_hi = np.percentile(aucs, [2.5, 97.5])
    acc_lo, acc_hi = np.percentile(accs, [2.5, 97.5])
    return {
        "n": len(y),
        "auc": roc_auc_score(y, p), "auc_ci_low": auc_lo, "auc_ci_high": auc_hi,
        "accuracy": accuracy_score(y, (p >= threshold).astype(int)),
        "acc_ci_low": acc_lo, "acc_ci_high": acc_hi,
        "auc_ci_includes_0.5": bool(auc_lo <= 0.5 <= auc_hi),
    }


def main() -> None:
    setup_logging("uncertainty")
    rows = []
    for path in sorted(REPORTS.glob("test_predictions_*.csv")):
        model = path.stem.replace("test_predictions_", "")
        df = pd.read_csv(path)
        rows.append({"model": model, **bootstrap_ci(df["y_true"], df["proba_underperform"])})
    if not rows:
        raise FileNotFoundError("no reports/test_predictions_*.csv; run the train stage first")
    out = pd.DataFrame(rows).round(3)
    out.to_csv(REPORTS / "test_uncertainty.csv", index=False)
    logger.info("\n%s", out.to_string(index=False))


if __name__ == "__main__":
    main()
