"""Feature-drift detection: Population Stability Index (PSI) + two-sample KS test.

A feature counts as drifted only if BOTH agree (PSI >= threshold AND KS p < alpha).
PSI alone is noisy with small batches; KS alone flags tiny, harmless shifts. Requiring
both keeps false alarms low. The batch as a whole drifts when a large enough share of
features has drifted. Thresholds live in params.yaml.
"""

from typing import Dict, Sequence

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp

EPS = 1e-4  # floor for empty bins so the log ratio stays finite
DEFAULT_SHIFT_SD = 1.5


def psi(reference: Sequence[float], current: Sequence[float], bins: int = 10) -> float:
    """PSI of `current` against `reference`, using reference-quantile bins.

    Rule of thumb: < 0.1 stable, 0.1-0.2 moderate shift, >= 0.2 significant shift.
    """
    ref = np.asarray(reference, dtype=float)
    cur = np.asarray(current, dtype=float)
    ref, cur = ref[~np.isnan(ref)], cur[~np.isnan(cur)]
    if len(ref) == 0 or len(cur) == 0:
        return float("nan")
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:  # (near-)constant reference cannot be binned
        return 0.0 if np.isclose(cur, ref[0]).mean() >= 0.99 else 1.0
    edges[0], edges[-1] = -np.inf, np.inf
    ref_p = np.clip(np.histogram(ref, edges)[0] / len(ref), EPS, None)
    cur_p = np.clip(np.histogram(cur, edges)[0] / len(cur), EPS, None)
    return float(np.sum((cur_p - ref_p) * np.log(cur_p / ref_p)))


def detect_drift(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    columns: Sequence[str],
    psi_threshold: float = 0.2,
    ks_alpha: float = 0.01,
    min_drifted_share: float = 0.25,
    bins: int = 10,
) -> Dict:
    """Per-feature PSI/KS results and a batch-level drift decision."""
    features: Dict[str, Dict] = {}
    for col in columns:
        r, c = reference[col].dropna(), current[col].dropna()
        if len(r) < 2 or len(c) < 2:
            features[col] = {"psi": None, "ks_stat": None, "ks_pvalue": None, "drifted": False}
            continue
        p = psi(r, c, bins)
        ks = ks_2samp(r, c)
        features[col] = {
            "psi": round(p, 4),
            "ks_stat": round(float(ks.statistic), 4),
            "ks_pvalue": round(float(ks.pvalue), 6),
            "drifted": bool(p >= psi_threshold and ks.pvalue < ks_alpha),
        }
    n_drifted = sum(f["drifted"] for f in features.values())
    psis = [f["psi"] for f in features.values() if f["psi"] is not None]
    share = n_drifted / len(columns) if len(columns) else 0.0
    return {
        "features": features,
        "n_features": len(columns),
        "n_drifted": n_drifted,
        "drifted_share": round(share, 4),
        "max_psi": round(max(psis), 4) if psis else 0.0,
        "drift_detected": bool(share >= min_drifted_share),
        "n_reference": int(len(reference)),
        "n_current": int(len(current)),
        "thresholds": {"psi": psi_threshold, "ks_alpha": ks_alpha, "min_drifted_share": min_drifted_share},
    }


def simulate_shift(
    current: pd.DataFrame, reference: pd.DataFrame, columns: Sequence[str], shift_sd: float = DEFAULT_SHIFT_SD
) -> pd.DataFrame:
    """Demo helper: move every feature by `shift_sd` reference standard deviations."""
    shifted = current.copy()
    for col in columns:
        shifted[col] = shifted[col] + shift_sd * reference[col].std()
    return shifted
