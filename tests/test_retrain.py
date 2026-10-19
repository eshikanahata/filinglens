import json
import math

import pytest

from src.common.run_log import log_event, read_events
from src.drift.retrain import decide_promotion, orchestrate


class FakeRunner:
    def __init__(self):
        self.calls = []

    def dvc(self, *args):
        self.calls.append(("dvc",) + args)

    def python_module(self, module, *args):
        self.calls.append(("python", module) + args)


class FakeRegistry:
    """Models the real behaviour: training registers a new version and moves the alias to it."""

    def __init__(self, champion="2", cv=None, new_cv=0.55):
        self.cv = cv or {"2": 0.52}
        self.champion, self.new_cv, self.runner = champion, new_cv, None

    def champion_version(self):
        return self.champion

    def latest_version(self):
        return str(max(int(v) for v in self.cv))

    def cv_auc(self, version):
        return self.cv.get(str(version))

    def set_champion(self, version):
        self.champion = str(version)

    def on_train(self):                       # called by FakeRunner hook below
        nxt = str(max(int(v) for v in self.cv) + 1)
        self.cv[nxt] = self.new_cv
        self.champion = nxt


class TrainingRunner(FakeRunner):
    def __init__(self, registry):
        super().__init__()
        self.registry = registry

    def dvc(self, *args):
        super().dvc(*args)
        if args[:4] == ("repro", "-f", "-s", "train"):
            self.registry.on_train()


def run(registry, drift=1, force=False, simulate=False, tolerance=0.01):
    events = []
    runner = TrainingRunner(registry)
    out = orchestrate(runner, registry, tolerance, force, simulate,
                      read_metrics=lambda: {"drift_detected": drift},
                      log=lambda event, status="ok", **d: events.append((event, status, d)) or d)
    return out, runner, events


def test_decide_promotion_rules():
    assert decide_promotion(0.52, 0.55, 0.01) == "promote"
    assert decide_promotion(0.52, 0.515, 0.01) == "promote"        # within tolerance
    assert decide_promotion(0.52, 0.45, 0.01) == "rollback"
    assert decide_promotion(None, 0.50, 0.01) == "promote"         # nothing to compare with
    assert decide_promotion(0.52, None, 0.01) == "rollback"
    assert decide_promotion(0.52, math.nan, 0.01) == "rollback"


def test_no_drift_no_retrain():
    reg = FakeRegistry()
    out, runner, events = run(reg, drift=0)
    assert out == {"drift_detected": False, "retrained": False}
    assert ("dvc", "repro", "drift") in runner.calls
    assert not any(c[:4] == ("dvc", "repro", "-f", "-s") for c in runner.calls) and events == []


def test_drift_triggers_retrain_and_promotes_better_model():
    reg = FakeRegistry(new_cv=0.56)
    out, runner, events = run(reg)
    assert out["retrained"] and out["decision"] == "promote" and out["serving_version"] == "3"
    assert [e[0] for e in events] == ["retrain_started", "model_promoted", "model_exported"]
    order = [c for c in runner.calls if c[:3] == ("dvc", "repro", "-f")]
    assert order == [("dvc", "repro", "-f", "-s", "train"), ("dvc", "repro", "-f", "-s", "export_model")]


def test_worse_model_is_rolled_back_to_previous_version():
    reg = FakeRegistry(new_cv=0.40)
    out, _, events = run(reg)
    assert out["decision"] == "rollback" and reg.champion == "2" and out["serving_version"] == "2"
    assert events[1][0] == "model_rollback" and events[1][1] == "warning"
    assert events[1][2]["rejected_version"] == "3" and events[1][2]["restored_version"] == "2"


def test_force_retrains_without_drift():
    out, _, events = run(FakeRegistry(), drift=0, force=True)
    assert out["retrained"] and out["reason"] == "forced" and events[0][2]["reason"] == "forced"


def test_simulate_shift_runs_check_directly_not_via_dvc():
    _, runner, _ = run(FakeRegistry(), simulate=True)
    assert runner.calls[0] == ("python", "src.drift.check_drift", "--simulate-shift")
    assert ("dvc", "repro", "drift") not in runner.calls


def test_event_log_roundtrip_newest_first_and_tolerates_garbage(tmp_path):
    path = tmp_path / "h.jsonl"
    log_event("a", path=path, x=1)
    log_event("b", "warning", path=path)
    path.write_text(path.read_text() + "not json\n")
    events = read_events(path)
    assert [e["event"] for e in events] == ["b", "a"] and events[1]["x"] == 1
    assert read_events(path, limit=1)[0]["event"] == "b"
    assert read_events(tmp_path / "missing.jsonl") == []


def test_real_mlflow_registry_champion_alias_and_rollback(tmp_path):
    """The actual MlflowRegistry against a real (temporary) MLflow store."""
    import mlflow
    import mlflow.sklearn
    import numpy as np
    import pandas as pd
    from mlflow.tracking import MlflowClient
    from sklearn.linear_model import LogisticRegression

    from src.drift.retrain import MlflowRegistry

    uri = f"sqlite:///{tmp_path}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    client = MlflowClient()
    exp = client.create_experiment("t", artifact_location=(tmp_path / "art").resolve().as_uri())
    X = pd.DataFrame(np.random.default_rng(0).normal(size=(40, 2)), columns=["a", "b"])
    model = LogisticRegression().fit(X, (X["a"] > 0).astype(int))
    for cv in (0.52, 0.40):                                   # version 1 (good), version 2 (worse)
        with mlflow.start_run(experiment_id=exp):
            mlflow.log_metric("cv_roc_auc", cv)
            info = mlflow.sklearn.log_model(model, name="model", serialization_format="cloudpickle")
        mv = mlflow.register_model(info.model_uri, "m")
        client.set_registered_model_alias("m", "champion", mv.version)   # training moves the alias

    reg = MlflowRegistry(uri, "m")
    assert reg.champion_version() == "2" and reg.latest_version() == "2"
    assert reg.cv_auc("1") == pytest.approx(0.52) and reg.cv_auc("2") == pytest.approx(0.40)
    assert decide_promotion(reg.cv_auc("1"), reg.cv_auc("2"), 0.01) == "rollback"
    reg.set_champion("1")                                     # the rollback itself
    assert reg.champion_version() == "1"
    assert MlflowRegistry(uri, "never-registered").champion_version() is None
    mlflow.set_tracking_uri("")
