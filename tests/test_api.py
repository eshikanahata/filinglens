import json

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api.model_client import ModelServerClient, ModelServerError

COLUMNS = ["neg_ratio", "unc_ratio", "tfidf_similarity", "risk_words_change",
           "d_neg_ratio", "d_unc_ratio", "d_lit_ratio", "d_fk_grade"]


def filing(ticker, acc, date, prior=None, sim=0.8, chg=0.05):
    has_prior = prior is not None
    feats = {c: 0.01 for c in COLUMNS}
    feats.update({"tfidf_similarity": sim if has_prior else None,
                  "risk_words_change": chg if has_prior else None})
    pcts = {"tfidf_similarity": 10.0, "risk_words_change": 90.0} if has_prior else {}
    return {"ticker": ticker, "accession": acc, "filing_date": date, "report_date": date,
            "has_prior": has_prior, "prior_accession": prior, "features": feats,
            "percentiles": pcts, "new_terms": ["supply chain"], "dropped_terms": ["covid"]}


class FakeModel:
    def __init__(self, scores=None, up=True):
        self.scores, self.up, self.calls = scores, up, []

    def ping(self):
        return self.up

    def predict_proba(self, columns, rows):
        self.calls.append((list(columns), len(rows)))
        if not self.up:
            raise ModelServerError("down")
        return self.scores[: len(rows)] if self.scores else [0.7] * len(rows)


@pytest.fixture
def env(tmp_path):
    filings = [filing("AAA", "a1", "2023-02-01"),
               filing("AAA", "a2", "2024-02-01", prior="a1"),
               filing("AAA", "a3", "2025-02-01", prior="a2"),
               filing("BBB", "b1", "2025-03-01")]
    (tmp_path / "serving.json").write_text(json.dumps({"feature_columns": COLUMNS, "filings": filings}))
    (tmp_path / "info.json").write_text(json.dumps({"champion_model": "xgboost", "version": "3",
                                                    "run_id": "abc", "test_roc_auc": 0.48}))
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "parse_metrics.json").write_text(json.dumps(
        {"workers": 4, "filings_total": 10, "filings_ok": 9, "filings_failed": 1,
         "success_rate": 0.9, "filings_per_minute": 300.0}))
    (reports / "ray_benchmark.json").write_text(json.dumps([{"workers": 1, "speedup_vs_1_worker": 1.0}]))
    return Settings(serving_data_path=str(tmp_path / "serving.json"),
                    model_info_path=str(tmp_path / "info.json"), reports_dir=str(reports))


def client(env, model=None):
    model = model or FakeModel()
    return TestClient(create_app(env, model_client=model)), model


def test_health_ok_and_degraded(env):
    c, _ = client(env)
    assert c.get("/health").json() == {"status": "ok", "model_server": "up", "filings_loaded": 4, "companies": 2}
    c2, _ = client(env, FakeModel(up=False))
    body = c2.get("/health").json()
    assert c2.get("/health").status_code == 200 and body["status"] == "degraded"


def test_tickers(env):
    c, _ = client(env)
    items = c.get("/tickers").json()["tickers"]
    assert [i["ticker"] for i in items] == ["AAA", "BBB"]
    assert items[0]["n_filings"] == 3 and items[0]["latest_filing_date"] == "2025-02-01"


def test_analysis_scored(env):
    c, model = client(env, FakeModel([0.72]))
    r = c.get("/analysis/aaa")                      # lower-case input is accepted
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAA" and body["filing"]["accession"] == "a3"
    assert body["previous_filing"]["accession"] == "a2"
    assert body["signal"] == {"label": "Elevated", "score": 0.72, "elevated_threshold": 0.6,
                              "low_threshold": 0.4}
    assert body["changes"]["new_terms"] == ["supply chain"]
    assert body["model"]["version"] == "3" and "decision support" in body["disclaimer"]
    assert len(body["reasons"]) >= 1
    assert model.calls == [(COLUMNS, 1)]


def test_analysis_without_prior_year_is_not_scored(env):
    c, model = client(env)
    body = c.get("/analysis/BBB").json()
    assert body["signal"]["label"] == "Not enough data" and body["signal"]["score"] is None
    assert "earliest filing" in body["reasons"][0]
    assert model.calls == []                         # model is not called when there is nothing to score


def test_unknown_and_invalid_ticker(env):
    c, _ = client(env)
    r = c.get("/analysis/ZZZZ")
    assert r.status_code == 404 and r.json()["error"]["code"] == "unknown_ticker"
    r = c.get("/analysis/12345")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_input"
    r = c.get("/analysis/AA;DROP")
    assert r.status_code == 400


def test_model_server_down_gives_friendly_503(env):
    c, _ = client(env, FakeModel(up=False))
    r = c.get("/analysis/AAA")
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    assert "Traceback" not in r.text


def test_history_batches_one_model_call(env):
    c, model = client(env, FakeModel([0.3, 0.8]))
    pts = c.get("/analysis/AAA/history").json()["points"]
    assert [p["accession"] for p in pts] == ["a1", "a2", "a3"]
    assert pts[0]["score"] is None and pts[0]["label"] == "Not enough data"
    assert pts[1]["label"] == "Lower" and pts[2]["label"] == "Elevated"
    assert model.calls == [(COLUMNS, 2)]             # a single batched request


def test_pipeline_endpoint(env):
    c, _ = client(env)
    body = c.get("/pipeline/runs").json()
    stages = {s["name"]: s for s in body["stages"]}
    assert stages["parse"]["status"] == "warning"    # 90% < 95% target
    assert stages["train"]["status"] == "missing"
    assert body["ray_benchmark"][0]["workers"] == 1
    assert body["champion"]["name"] == "xgboost"


def test_metrics_endpoint_exposes_expected_series(env):
    c, _ = client(env, FakeModel([0.5]))
    c.get("/analysis/AAA")
    c.get("/analysis/ZZZ")
    text = c.get("/metrics").text
    assert 'filinglens_http_requests_total{endpoint="/analysis/{ticker}",method="GET",status="200"} 1.0' in text
    assert 'status="404"' in text
    assert "filinglens_http_request_duration_seconds_bucket" in text
    assert 'filinglens_model_requests_total{outcome="success"} 1.0' in text
    assert "filinglens_risk_score_bucket" in text
    assert 'filinglens_pipeline_filings{outcome="failed",stage="parse"} 1.0' in text
    assert "filinglens_parse_success_ratio 0.9" in text
    assert 'filinglens_model_info{model="xgboost",version="3"} 1.0' in text


def test_missing_serving_data_fails_fast(tmp_path):
    with pytest.raises(FileNotFoundError, match="dvc repro"):
        create_app(Settings(serving_data_path=str(tmp_path / "nope.json")))


def test_model_client_parses_probabilities_and_rejects_labels():
    class Resp:
        def __init__(self, payload): self.payload = payload
        def raise_for_status(self): pass
        def json(self): return self.payload

    class Session:
        def __init__(self, payload): self.payload = payload
        def post(self, *a, **k): return Resp(self.payload)

    ok = ModelServerClient("http://x", session=Session({"predictions": [[0.3, 0.7], [0.9, 0.1]]}))
    assert ok.predict_proba(["a"], [[1], [2]]) == [0.7, 0.1]
    labels = ModelServerClient("http://x", session=Session({"predictions": [0, 1]}))
    with pytest.raises(ModelServerError, match="probabilities"):
        labels.predict_proba(["a"], [[1], [2]])
