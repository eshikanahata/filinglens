"""Drift and events flowing through backend, Prometheus config, Grafana and the console."""
import json
import re
from pathlib import Path

import pytest
import requests
import yaml
from streamlit.testing.v1 import AppTest

from tests.test_api import FakeModel, client, env  # noqa: F401  (env is a pytest fixture)
from tests.test_frontend_app import APP, PIPELINE, Resp, fake_get

ROOT = Path(__file__).resolve().parent.parent
DRIFT_REPORT = {"status": "ok", "simulated": True, "drift_detected": True, "n_features": 2, "n_drifted": 2,
                "drifted_share": 1.0, "max_psi": 0.31, "n_reference": 100, "n_current": 40,
                "features": {"unc_ratio": {"psi": 0.31, "ks_stat": 0.4, "ks_pvalue": 0.0001, "drifted": True},
                             "neg_ratio": {"psi": 0.05, "ks_stat": 0.1, "ks_pvalue": 0.4, "drifted": False}}}


@pytest.fixture
def with_drift(env):  # noqa: F811
    reports = Path(env.reports_dir)
    (reports / "drift_metrics.json").write_text(json.dumps(
        {"drift_detected": 1, "drifted_features": 2, "drifted_share": 1.0, "max_psi": 0.31, "simulated": 1}))
    (reports / "drift_report.json").write_text(json.dumps(DRIFT_REPORT))
    events = [{"ts": f"2026-10-1{i}T10:00:00+00:00", "event": e, "status": s}
              for i, (e, s) in enumerate([("drift_check", "drift"), ("retrain_started", "ok"),
                                          ("model_rollback", "warning")])]
    (reports / "run_history.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return env


def test_pipeline_endpoint_includes_drift_and_events_newest_first(with_drift):
    c, _ = client(with_drift)
    body = c.get("/pipeline/runs").json()
    stages = {s["name"]: s for s in body["stages"]}
    assert stages["drift"]["status"] == "warning"
    assert body["drift_report"]["n_drifted"] == 2
    assert [e["event"] for e in body["events"]] == ["model_rollback", "retrain_started", "drift_check"]


def test_prometheus_exposes_drift_and_event_metrics(with_drift):
    c, _ = client(with_drift)
    text = c.get("/metrics").text
    assert "filinglens_drift_detected 1.0" in text
    assert 'filinglens_drift_psi{feature="unc_ratio"} 0.31' in text
    assert "filinglens_drift_max_psi 0.31" in text
    assert 'filinglens_pipeline_events{event="model_rollback"} 1.0' in text


def test_backend_tolerates_missing_drift_files(env):  # noqa: F811
    c, _ = client(env)
    body = c.get("/pipeline/runs").json()
    assert body["drift_report"] is None and body["events"] == []
    assert {s["name"]: s["status"] for s in body["stages"]}["drift"] == "missing"
    assert c.get("/metrics").status_code == 200


# ---------- static config checks ----------
ALERTS = yaml.safe_load((ROOT / "monitoring/alerts.yml").read_text())
RULES = [r for g in ALERTS["groups"] for r in g["rules"]]
METRICS_SRC = (ROOT / "api/metrics.py").read_text()


def defined(name):
    return f'"{re.sub(r"_(bucket|sum|count)$", "", name)}"' in METRICS_SRC


def test_alert_rules_reference_exported_metrics_and_are_unique():
    names = [r["alert"] for r in RULES]
    assert len(names) == len(set(names)) and {"BackendDown", "DataDriftDetected", "ModelServerErrors"} <= set(names)
    for r in RULES:
        for metric in re.findall(r"filinglens_[a-z_]+", r["expr"]):
            assert defined(metric), f"{r['alert']} uses undefined metric {metric}"
        assert r["labels"]["severity"] in ("critical", "warning") and r["annotations"]["summary"]


def test_prometheus_loads_the_alert_rules_file_that_compose_mounts():
    prom = yaml.safe_load((ROOT / "monitoring/prometheus.yml").read_text())
    mounts = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["prometheus"]["volumes"]
    target = prom["rule_files"][0]
    assert any(m.split(":")[1] == target and m.split(":")[0].endswith("alerts.yml") for m in mounts)


def test_drift_dashboard_panels_exist_and_use_defined_metrics():
    dash = json.loads((ROOT / "monitoring/grafana/dashboards/filinglens.json").read_text())
    by_id = {p["id"]: p for p in dash["panels"]}
    assert {12, 13, 14} <= set(by_id) and len(by_id) == len(dash["panels"])
    for pid in (12, 13, 14):
        for metric in re.findall(r"filinglens_[a-z_]+", by_id[pid]["targets"][0]["expr"]):
            assert defined(metric)


def test_mlflow_ui_never_tries_to_pull_the_locally_built_image():
    svc = yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"]["mlflow-ui"]
    assert svc["image"] == "filinglens-model:latest" and svc["pull_policy"] == "never"


def test_dvc_drift_stage_is_wired_to_params_and_metrics():
    stages = yaml.safe_load((ROOT / "dvc.yaml").read_text())["stages"]
    d = stages["drift"]
    assert "drift" in d["params"] and "reports/drift_report.json" in " ".join(map(str, d["outs"]))
    assert "reports/drift_metrics.json" in " ".join(map(str, d["metrics"]))
    assert "train" not in str(d["deps"])            # drift must not depend on (or trigger) training
    params = yaml.safe_load((ROOT / "params.yaml").read_text())
    assert {"psi_threshold", "ks_alpha", "min_drifted_share"} <= set(params["drift"])
    assert "promotion_tolerance" in params["retrain"]


# ---------- console page ----------
def test_console_shows_drift_warning_and_events(monkeypatch):
    import streamlit as st
    st.cache_data.clear()
    payload = {**PIPELINE, "drift_report": DRIFT_REPORT,
               "events": [{"ts": "2026-10-17T10:00:00+00:00", "event": "model_rollback", "status": "warning"}]}

    def get(url, timeout):
        return Resp(200, payload) if url.endswith("/pipeline/runs") else fake_get(url, timeout)

    monkeypatch.setattr(requests, "get", get)
    at = AppTest.from_file(APP, default_timeout=20).run()
    at.sidebar.radio[0].set_value("Pipeline console").run()
    assert not at.exception
    assert {"Data drift", "Recent pipeline events"} <= {s.value for s in at.subheader}
    assert any("deliberately shifted" in w.value for w in at.warning)
    assert any(m.label == "Drift detected" and m.value == "YES" for m in at.metric)
