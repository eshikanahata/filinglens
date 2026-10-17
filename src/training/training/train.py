"""DVC stage `train`: compare models, track everything in MLflow, register a champion.

Models: majority-class baseline, logistic regression, XGBoost.
Selection uses expanding-window (time-ordered) cross-validation INSIDE the training
period, never the test set. Test metrics are reported for every model afterwards.
Reproducibility: each run is tagged with the Git commit and data hashes.
"""
import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import mlflow
import mlflow.sklearn
import numpy as np
import pandas as pd
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.base import BaseEstimator, clone
from sklearn.dummy import DummyClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, f1_score, precision_score,
    recall_score, roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from src.common.config import load_params, setup_logging
from src.features.columns import FEATURE_COLUMNS
from src.training.dataset import build_dataset

logger = logging.getLogger(__name__)

FEATURES = Path("data/features/features.csv")
LABELS = Path("data/labels/labels.csv")
REPORTS = Path("reports")


def git_info() -> Dict[str, str]:
    """Commit hash and whether the working tree has uncommitted changes."""
    def run(*args: str) -> Optional[str]:
        try:
            return subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            return None
    commit = run("rev-parse", "HEAD") or "unknown"
    dirty = bool(run("status", "--porcelain"))
    return {"git_commit": commit, "git_dirty": str(dirty)}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_models(cfg: Dict) -> Dict[str, BaseEstimator]:
    seed = cfg["random_state"]
    return {
        "majority_baseline": DummyClassifier(strategy="most_frequent"),
        "logistic_regression": Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(C=cfg["logreg"]["C"], class_weight="balanced",
                                       max_iter=1000, random_state=seed)),
        ]),
        "xgboost": XGBClassifier(**cfg["xgboost"], eval_metric="logloss", n_jobs=1,
                                 random_state=seed),
    }


def time_cv_auc(model: BaseEstimator, X: pd.DataFrame, y: pd.Series, n_splits: int) -> float:
    """Mean ROC-AUC over expanding-window folds (data must be sorted by time)."""
    scores: List[float] = []
    for tr, va in TimeSeriesSplit(n_splits=n_splits).split(X):
        if y.iloc[tr].nunique() < 2 or y.iloc[va].nunique() < 2:
            continue
        m = clone(model).fit(X.iloc[tr], y.iloc[tr])
        scores.append(roc_auc_score(y.iloc[va], m.predict_proba(X.iloc[va])[:, 1]))
    return float(np.mean(scores)) if scores else float("nan")


def evaluate(model: BaseEstimator, X: pd.DataFrame, y: pd.Series) -> Dict[str, float]:
    pred = model.predict(X)
    proba = model.predict_proba(X)[:, 1]
    return {
        "accuracy": accuracy_score(y, pred),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
        "roc_auc": roc_auc_score(y, proba),
        "precision": precision_score(y, pred, zero_division=0),
        "recall": recall_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
    }


def feature_importance(name: str, model: BaseEstimator) -> Optional[pd.DataFrame]:
    if name == "logistic_regression":
        vals = np.abs(model.named_steps["clf"].coef_[0])      # features are standardised
    elif name == "xgboost":
        vals = model.feature_importances_
    else:
        return None
    return pd.DataFrame({"feature": FEATURE_COLUMNS, "importance": vals}).sort_values(
        "importance", ascending=False)


def log_model_compat(model: BaseEstimator, X: pd.DataFrame) -> str:
    """MLflow 3 renamed artifact_path to name; support both.

    cloudpickle is used because MLflow 3's default (skops) rejects XGBoost's numpy
    types. Acceptable here: models are produced and loaded locally by this project.
    pyfunc_predict_fn="predict_proba" makes the served endpoint return class
    probabilities (the backend needs P(underperform), not a hard 0/1 label).
    """
    sig = infer_signature(X, model.predict_proba(X))
    try:
        info = mlflow.sklearn.log_model(model, name="model", signature=sig,
                                        input_example=X.head(3),
                                        serialization_format="cloudpickle",
                                        pyfunc_predict_fn="predict_proba")
    except TypeError:
        info = mlflow.sklearn.log_model(model, artifact_path="model", signature=sig,
                                        input_example=X.head(3),
                                        serialization_format="cloudpickle",
                                        pyfunc_predict_fn="predict_proba")
    return info.model_uri


def setup_mlflow(cfg: Dict) -> None:
    mlflow.set_tracking_uri(cfg["tracking_uri"])
    client = MlflowClient()
    if client.get_experiment_by_name(cfg["experiment_name"]) is None:
        client.create_experiment(cfg["experiment_name"],
                                 artifact_location=Path("mlartifacts").resolve().as_uri())
    mlflow.set_experiment(cfg["experiment_name"])


def run_model(name: str, model: BaseEstimator, cv_auc: float, data: Dict, params: Dict,
              extra_tags: Dict[str, str], info: Dict) -> Dict:
    """Train one model inside an MLflow run and log params, metrics and artifacts."""
    Xtr, ytr, Xte, yte = data["Xtr"], data["ytr"], data["Xte"], data["yte"]
    with mlflow.start_run(run_name=name) as run:
        mlflow.set_tags({"model": name, **extra_tags})
        mlflow.log_params({
            "model_name": name, "n_features": len(FEATURE_COLUMNS),
            "label_horizon_days": params["labels"]["horizon_trading_days"],
            "split_test_start": info["test_start"], "split_train_end": info["train_end"],
            "n_train": info["n_train"], "n_test": info["n_test"],
            "seed": params["train"]["random_state"],
        })
        # Autolog only around the final fit so cross-validation fits stay out of the run.
        mlflow.sklearn.autolog(log_models=False, log_datasets=False,
                               log_post_training_metrics=False, silent=True)
        model.fit(Xtr, ytr)
        mlflow.sklearn.autolog(disable=True)

        test = evaluate(model, Xte, yte)
        train = evaluate(model, Xtr, ytr)
        mlflow.log_metrics({f"test_{k}": v for k, v in test.items()})
        mlflow.log_metrics({f"train_{k}": v for k, v in train.items()})
        mlflow.log_metric("cv_roc_auc", cv_auc)

        REPORTS.mkdir(exist_ok=True)
        imp = feature_importance(name, model)
        if imp is not None:
            path = REPORTS / f"importance_{name}.csv"
            imp.to_csv(path, index=False)
            mlflow.log_artifact(str(path), "explainability")
        preds = data["test_meta"].assign(y_true=yte.values,
                                         proba_underperform=model.predict_proba(Xte)[:, 1])
        path = REPORTS / f"test_predictions_{name}.csv"
        preds.to_csv(path, index=False)
        mlflow.log_artifact(str(path), "predictions")
        model_uri = log_model_compat(model, Xtr)
        return {"model": name, "run_id": run.info.run_id, "model_uri": model_uri,
                "cv_roc_auc": cv_auc,
                **{f"test_{k}": v for k, v in test.items()}}


def main() -> None:
    setup_logging("train")
    params = load_params()
    tcfg = params["train"]

    features = pd.read_csv(FEATURES)
    labels = pd.read_csv(LABELS)
    train_df, test_df, info = build_dataset(features, labels, params["split"])
    logger.info("Dataset: %s", info)

    data = {
        "Xtr": train_df[FEATURE_COLUMNS].reset_index(drop=True),
        "ytr": train_df["target"].reset_index(drop=True),
        "Xte": test_df[FEATURE_COLUMNS].reset_index(drop=True),
        "yte": test_df["target"].reset_index(drop=True),
        "test_meta": test_df[["ticker", "accession", "filing_date"]].reset_index(drop=True),
    }
    models = build_models(tcfg)
    cv = {n: (0.5 if n == "majority_baseline"
              else time_cv_auc(m, data["Xtr"], data["ytr"], tcfg["cv_splits"]))
          for n, m in models.items()}
    logger.info("Time-ordered CV ROC-AUC: %s", {k: round(v, 3) for k, v in cv.items()})

    tags = {**git_info(), "features_sha256": file_sha256(FEATURES),
            "labels_sha256": file_sha256(LABELS)}
    setup_mlflow(params["mlflow"])
    results = [run_model(n, m, cv[n], data, params, tags, info) for n, m in models.items()]
    table = pd.DataFrame(results)

    candidates = table[table["model"] != "majority_baseline"].dropna(subset=["cv_roc_auc"])
    if candidates.empty:
        raise RuntimeError("no candidate model produced a valid CV score")
    champ = candidates.sort_values("cv_roc_auc", ascending=False).iloc[0]
    base = table[table["model"] == "majority_baseline"].iloc[0]

    reg_name = params["mlflow"]["registered_model_name"]
    version = mlflow.register_model(champ["model_uri"], reg_name)
    MlflowClient().set_registered_model_alias(reg_name, "champion", version.version)
    logger.info("Champion: %s (CV AUC %.3f) -> %s v%s", champ["model"], champ["cv_roc_auc"],
                reg_name, version.version)

    REPORTS.mkdir(exist_ok=True)
    table.to_csv(REPORTS / "model_comparison.csv", index=False)
    metrics = {
        "champion_cv_roc_auc": round(float(champ["cv_roc_auc"]), 4),
        "champion_test_roc_auc": round(float(champ["test_roc_auc"]), 4),
        "champion_test_accuracy": round(float(champ["test_accuracy"]), 4),
        "baseline_test_accuracy": round(float(base["test_accuracy"]), 4),
        "beats_baseline_accuracy": int(champ["test_accuracy"] > base["test_accuracy"]),
        "n_train": info["n_train"], "n_test": info["n_test"],
    }
    (REPORTS / "train_metrics.json").write_text(json.dumps(metrics, indent=2))
    (REPORTS / "train_run.json").write_text(json.dumps({
        "champion_model": champ["model"], "champion_run_id": champ["run_id"],
        "registered_model": reg_name, "registered_version": str(version.version),
        **tags}, indent=2))
    logger.info("Done: %s", metrics)


if __name__ == "__main__":
    main()
