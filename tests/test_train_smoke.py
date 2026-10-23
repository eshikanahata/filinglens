"""End-to-end smoke test of the train stage on synthetic data (uses a temp MLflow DB)."""

import pytest

pytest.importorskip("mlflow")
pytest.importorskip("xgboost")

import mlflow  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402

from src.training import train as train_mod  # noqa: E402
from tests.test_dataset_split import synthetic  # noqa: E402


def test_train_stage_runs_and_registers_champion(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    feats, labels = synthetic(n=240)
    (tmp_path / "data/features").mkdir(parents=True)
    (tmp_path / "data/labels").mkdir(parents=True)
    feats.to_csv(tmp_path / "data/features/features.csv", index=False)
    labels.to_csv(tmp_path / "data/labels/labels.csv", index=False)

    params = {
        "labels": {"horizon_trading_days": 30},
        "split": {"test_start_date": "2025-07-01", "embargo_days": 45},
        "train": {
            "random_state": 0,
            "cv_splits": 3,
            "logreg": {"C": 1.0},
            "xgboost": {
                "n_estimators": 20,
                "max_depth": 2,
                "learning_rate": 0.1,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
            },
        },
        "mlflow": {
            "tracking_uri": f"sqlite:///{tmp_path}/mlflow.db",
            "experiment_name": "smoke",
            "registered_model_name": "smoke-model",
        },
    }
    monkeypatch.setattr(train_mod, "load_params", lambda *a, **k: params)
    train_mod.main()

    client = MlflowClient(tracking_uri=params["mlflow"]["tracking_uri"])
    mv = client.get_model_version_by_alias("smoke-model", "champion")
    assert str(mv.version) == "1"
    exp = client.get_experiment_by_name("smoke")
    runs = client.search_runs([exp.experiment_id])
    assert len(runs) == 3
    for r in runs:
        assert "git_commit" in r.data.tags and "features_sha256" in r.data.tags
        assert "test_roc_auc" in r.data.metrics
    assert (tmp_path / "reports/train_metrics.json").exists()
    mlflow.set_tracking_uri("")
