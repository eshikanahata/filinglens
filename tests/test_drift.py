import json

import numpy as np
import pandas as pd
import pytest

from src.drift import check_drift
from src.drift.drift import detect_drift, psi, simulate_shift
from src.features.columns import FEATURE_COLUMNS
from tests.test_dataset_split import synthetic

PARAMS = {
    "split": {"test_start_date": "2025-07-01", "embargo_days": 45},
    "drift": {"psi_threshold": 0.2, "ks_alpha": 0.01, "min_drifted_share": 0.25, "bins": 10,
              "min_current_samples": 20, "current_start_date": None},
}


def test_psi_is_near_zero_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    ref = rng.normal(size=2000)
    assert psi(ref, rng.normal(size=2000)) < 0.05
    assert psi(ref, rng.normal(loc=1.5, size=2000)) > 0.5


def test_psi_handles_nan_empty_and_constant_reference():
    assert np.isnan(psi([], [1.0, 2.0]))
    assert psi([1, 2, np.nan, 3] * 5, [1, 2, 3] * 5) < 0.2        # NaNs ignored
    assert psi([5.0] * 30, [5.0] * 30) == 0.0                      # constant, unchanged
    assert psi([5.0] * 30, [9.0] * 30) == 1.0                      # constant reference, moved away


def frames(shift=0.0, n_ref=300, n_cur=60, seed=1):
    rng = np.random.default_rng(seed)
    ref = pd.DataFrame(rng.normal(size=(n_ref, 4)), columns=list("abcd"))
    cur = pd.DataFrame(rng.normal(size=(n_cur, 4)) + shift, columns=list("abcd"))
    return ref, cur


def test_no_drift_for_same_distribution():
    ref, cur = frames(shift=0.0)
    out = detect_drift(ref, cur, list("abcd"))
    assert out["drift_detected"] is False and out["n_drifted"] == 0


def test_drift_detected_for_shifted_batch():
    ref, cur = frames(shift=1.5)
    out = detect_drift(ref, cur, list("abcd"))
    assert out["drift_detected"] is True and out["n_drifted"] == 4 and out["max_psi"] > 0.2


def test_feature_needs_both_psi_and_ks_to_count():
    ref, cur = frames(shift=1.5)
    strict_psi = detect_drift(ref, cur, list("abcd"), psi_threshold=50.0)       # PSI never reaches 50
    strict_ks = detect_drift(ref, cur, list("abcd"), ks_alpha=1e-300)           # KS never that significant
    assert strict_psi["n_drifted"] == 0 and strict_ks["n_drifted"] == 0


def test_share_threshold_decides_batch_level_flag():
    ref, cur = frames(shift=0.0)
    cur["a"] = cur["a"] + 3.0                                  # only 1 of 4 features moves
    assert detect_drift(ref, cur, list("abcd"), min_drifted_share=0.25)["drift_detected"] is True
    assert detect_drift(ref, cur, list("abcd"), min_drifted_share=0.5)["drift_detected"] is False


def test_simulate_shift_moves_every_column_by_sd_multiples():
    ref, cur = frames()
    shifted = simulate_shift(cur, ref, list("abcd"), shift_sd=2.0)
    assert np.allclose(shifted["a"] - cur["a"], 2.0 * ref["a"].std())
    assert not shifted.equals(cur)


def test_select_batches_uses_periods_and_requires_prior():
    feats, _ = synthetic()
    feats.loc[:10, "has_prior"] = False
    ref, cur = check_drift.select_batches(feats, PARAMS["split"], PARAMS["drift"])
    assert pd.to_datetime(ref["filing_date"]).max() <= pd.Timestamp("2025-05-17")
    assert pd.to_datetime(cur["filing_date"]).min() >= pd.Timestamp("2025-07-01")
    assert ref["has_prior"].all() and cur["has_prior"].all()


def test_run_check_real_batch_not_drifted_but_simulated_batch_is():
    feats, _ = synthetic(n=400)
    real = check_drift.run_check(feats, PARAMS)
    assert real["status"] == "ok" and real["drift_detected"] is False and real["simulated"] is False
    fake = check_drift.run_check(feats, PARAMS, simulate=True)
    assert fake["drift_detected"] is True and fake["simulated"] is True        # acceptance criterion


def test_run_check_reports_insufficient_data():
    feats, _ = synthetic(n=200)
    feats["filing_date"] = "2022-01-01"                         # nothing in the current period
    out = check_drift.run_check(feats, PARAMS)
    assert out["status"] == "insufficient_data" and out["drift_detected"] is False


def test_write_reports_and_main_log_event(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/features").mkdir(parents=True)
    feats, _ = synthetic(n=400)
    feats.to_csv(tmp_path / "data/features/features.csv", index=False)
    monkeypatch.setattr(check_drift, "load_params", lambda *a, **k: PARAMS)
    monkeypatch.setattr("sys.argv", ["check_drift", "--simulate-shift"])
    check_drift.main()
    metrics = json.loads((tmp_path / "reports/drift_metrics.json").read_text())
    assert metrics["drift_detected"] == 1 and metrics["simulated"] == 1
    report = json.loads((tmp_path / "reports/drift_report.json").read_text())
    assert set(report["features"]) == set(FEATURE_COLUMNS)
    events = [json.loads(line) for line in (tmp_path / "reports/run_history.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "drift_check" and events[-1]["status"] == "drift"
