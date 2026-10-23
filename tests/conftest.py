"""Shared pytest fixtures."""

import pytest

# Set by `mlflow run`; tests use their own temporary tracking stores, so these must not leak in.
_MLFLOW_ENV_VARS = ("MLFLOW_RUN_ID", "MLFLOW_EXPERIMENT_ID", "MLFLOW_EXPERIMENT_NAME", "MLFLOW_TRACKING_URI")


@pytest.fixture(autouse=True)
def isolated_mlflow_env(monkeypatch):
    """Run every test without the MLflow run context that `mlflow run` injects."""
    for name in _MLFLOW_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
