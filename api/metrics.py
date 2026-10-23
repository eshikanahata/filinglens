"""Prometheus instrumentation.

Request and model-server metrics are updated inline. Pipeline metrics are read from
the DVC stage reports at scrape time (a custom collector), so the pipeline needs no
push gateway and the numbers always match the latest `dvc repro`.
"""

from pathlib import Path

from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_client.core import GaugeMetricFamily

from api.pipeline_status import collect, read_events, read_json


class PipelineCollector:
    def __init__(self, reports_dir: str, model_info_path: str) -> None:
        self.reports_dir = reports_dir
        self.model_info_path = model_info_path

    def collect(self):
        data = collect(self.reports_dir)
        by_name = {s["name"]: s["metrics"] for s in data["stages"]}

        stage = GaugeMetricFamily(
            "filinglens_pipeline_filings", "Filings per pipeline stage and outcome", labels=["stage", "outcome"]
        )
        for name in ("download", "parse"):
            m = by_name.get(name) or {}
            if m:
                stage.add_metric([name, "ok"], m.get("filings_ok", 0))
                stage.add_metric([name, "failed"], m.get("filings_failed", 0))
        yield stage

        singles = [
            ("filinglens_parse_success_ratio", "Share of filings parsed successfully", "parse", "success_rate"),
            ("filinglens_parse_filings_per_minute", "Parsing throughput", "parse", "filings_per_minute"),
            ("filinglens_parse_workers", "Ray workers used in last parse", "parse", "workers"),
            (
                "filinglens_labels_positive_rate",
                "Share of labelled filings that underperformed",
                "labels",
                "positive_rate",
            ),
            ("filinglens_labels_unlabeled", "Filings without a label yet", "labels", "filings_unlabeled"),
            ("filinglens_train_champion_test_roc_auc", "Champion test ROC-AUC", "train", "champion_test_roc_auc"),
            ("filinglens_train_champion_cv_roc_auc", "Champion CV ROC-AUC", "train", "champion_cv_roc_auc"),
            ("filinglens_train_samples", "Training samples", "train", "n_train"),
            (
                "filinglens_drift_detected",
                "1 if the latest batch drifted from the training data",
                "drift",
                "drift_detected",
            ),
            ("filinglens_drift_features_drifted", "Number of drifted features", "drift", "drifted_features"),
            ("filinglens_drift_max_psi", "Largest per-feature PSI", "drift", "max_psi"),
            (
                "filinglens_drift_simulated",
                "1 if the drift report used a deliberately shifted batch",
                "drift",
                "simulated",
            ),
        ]
        for metric, doc, stage_name, key in singles:
            value = (by_name.get(stage_name) or {}).get(key)
            if value is not None:
                g = GaugeMetricFamily(metric, doc)
                g.add_metric([], float(value))
                yield g

        bench = GaugeMetricFamily("filinglens_ray_speedup", "Parsing speedup vs 1 worker", labels=["workers"])
        for row in data["ray_benchmark"]:
            bench.add_metric([str(row["workers"])], float(row["speedup_vs_1_worker"]))
        yield bench

        psi = GaugeMetricFamily("filinglens_drift_psi", "Population Stability Index per feature", labels=["feature"])
        for name, f in ((data.get("drift_report") or {}).get("features") or {}).items():
            if f.get("psi") is not None:
                psi.add_metric([name], float(f["psi"]))
        yield psi

        events = GaugeMetricFamily(
            "filinglens_pipeline_events", "Pipeline events logged so far, by type", labels=["event"]
        )
        counts: dict = {}
        for e in read_events(self.reports_dir):
            counts[e.get("event", "unknown")] = counts.get(e.get("event", "unknown"), 0) + 1
        for name, n in counts.items():
            events.add_metric([name], float(n))
        yield events

        info = read_json(Path(self.model_info_path))
        model = GaugeMetricFamily(
            "filinglens_model_info", "Currently served model (value is always 1)", labels=["model", "version"]
        )
        if info:
            model.add_metric([str(info.get("champion_model", "unknown")), str(info.get("version", "?"))], 1.0)
        yield model


class Metrics:
    """One registry per app instance (keeps tests independent)."""

    def __init__(self, reports_dir: str, model_info_path: str) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "filinglens_http_requests_total", "HTTP requests", ["method", "endpoint", "status"], registry=self.registry
        )
        self.latency = Histogram(
            "filinglens_http_request_duration_seconds", "HTTP request latency", ["endpoint"], registry=self.registry
        )
        self.model_calls = Counter(
            "filinglens_model_requests_total", "Calls to the model server", ["outcome"], registry=self.registry
        )
        self.model_latency = Histogram(
            "filinglens_model_latency_seconds", "Model server latency", registry=self.registry
        )
        self.score = Histogram(
            "filinglens_risk_score",
            "Distribution of returned risk scores",
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=self.registry,
        )
        self.analyses = Counter(
            "filinglens_analysis_total", "Analyses served by signal label", ["signal"], registry=self.registry
        )
        self.registry.register(PipelineCollector(reports_dir, model_info_path))
