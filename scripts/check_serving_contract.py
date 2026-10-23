"""Smoke check: serve an exported model with the real MLflow server and call it through the
backend client. Verifies the predict_proba contract end to end (no Docker needed).
Run:  PYTHONPATH=. python scripts/check_serving_contract.py
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path
import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from src.features.columns import FEATURE_COLUMNS
from src.training.train import build_models, log_model_compat
from src.serving.export_model import export_champion
from api.model_client import ModelServerClient

tmp = Path(tempfile.mkdtemp())
uri = f"sqlite:///{tmp}/mlflow.db"
mlflow.set_tracking_uri(uri)
client = MlflowClient()
exp = client.create_experiment("t", artifact_location=(tmp / "art").resolve().as_uri())
rng = np.random.default_rng(0)
X = pd.DataFrame(rng.normal(size=(200, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
y = pd.Series((X["unc_ratio"] + rng.normal(scale=0.5, size=200) > 0).astype(int))
cfg = {
    "random_state": 0,
    "logreg": {"C": 1.0},
    "xgboost": {"n_estimators": 30, "max_depth": 2, "learning_rate": 0.1, "subsample": 0.9, "colsample_bytree": 0.9},
}
results = {}
for name in ("xgboost", "logistic_regression"):
    model = build_models(cfg)[name].fit(X, y)
    with mlflow.start_run(experiment_id=exp):
        model_uri = log_model_compat(model, X)
    mv = mlflow.register_model(model_uri, f"m-{name}")
    client.set_registered_model_alias(f"m-{name}", "champion", mv.version)
    dst = tmp / name / "champion"
    export_champion(uri, f"m-{name}", "champion", dst)
    port = 5111 if name == "xgboost" else 5112
    proc = subprocess.Popen(
        [
            "mlflow",
            "models",
            "serve",
            "-m",
            str(dst),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--env-manager",
            "local",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        mc = ModelServerClient(f"http://127.0.0.1:{port}", timeout=10)
        for _ in range(60):
            if mc.ping():
                break
            time.sleep(1)
        else:
            proc.terminate()
            print(proc.stdout.read()[-2000:])
            sys.exit(f"{name}: server never came up")
        rows = X.head(3).values.tolist()
        probs = mc.predict_proba(FEATURE_COLUMNS, rows)
        expected = model.predict_proba(X.head(3))[:, 1]
        ok = np.allclose(probs, expected, atol=1e-5)
        print(f"{name}: ping ok, probs={np.round(probs, 4).tolist()}, matches local model: {ok}")
        results[name] = ok
        # a request containing a missing value, as the backend would send for a NaN feature
        bad = X.head(1).values.tolist()
        bad[0][2] = None
        try:
            print(f"{name}: null feature ->", np.round(mc.predict_proba(FEATURE_COLUMNS, bad), 4).tolist())
        except Exception as e:
            print(f"{name}: null feature -> ModelServerError ({str(e)[:120]})")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
print("ALL OK" if all(results.values()) else "MISMATCH")
