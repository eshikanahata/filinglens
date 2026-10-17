import json

import mlflow
import mlflow.pyfunc
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LogisticRegression

from src.serving.export_model import build_info, export_champion


def test_export_champion_is_portable_and_serves_probabilities(tmp_path):
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    client = MlflowClient()
    exp = client.create_experiment("t", artifact_location=(tmp_path / "art").resolve().as_uri())
    X = pd.DataFrame(np.random.default_rng(0).normal(size=(60, 3)), columns=["a", "b", "c"])
    y = (X["a"] > 0).astype(int)
    model = LogisticRegression().fit(X, y)
    with mlflow.start_run(experiment_id=exp):
        info = mlflow.sklearn.log_model(model, name="model", serialization_format="cloudpickle",
                                        pyfunc_predict_fn="predict_proba")
    mv = mlflow.register_model(info.model_uri, "m")
    client.set_registered_model_alias("m", "champion", mv.version)

    dst = tmp_path / "models" / "champion"
    version = export_champion(uri, "m", "champion", dst)
    assert version == str(mv.version) and (dst / "MLmodel").exists()

    loaded = mlflow.pyfunc.load_model(str(dst))            # loads from the copy, not the registry
    out = np.asarray(loaded.predict(X.head(5)))
    assert out.shape == (5, 2)                             # class probabilities, not labels
    assert np.allclose(out.sum(axis=1), 1.0)
    mlflow.set_tracking_uri("")


def test_build_info():
    info = build_info("4", "champion", {"registered_model": "m", "champion_model": "xgboost",
                                        "champion_run_id": "r1", "git_commit": "abc"},
                      {"champion_test_roc_auc": 0.48, "champion_cv_roc_auc": 0.52})
    assert info["version"] == "4" and info["champion_model"] == "xgboost"
    assert info["test_roc_auc"] == 0.48
    json.dumps(info)
