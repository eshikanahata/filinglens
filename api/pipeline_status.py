"""Read pipeline reports (written by the DVC stages) for the console and Prometheus."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STAGES = [
    ("download", "download_metrics.json"),
    ("parse", "parse_metrics.json"),
    ("prices", "prices_metrics.json"),
    ("labels", "labels_metrics.json"),
    ("features", "features_metrics.json"),
    ("train", "train_metrics.json"),
    ("drift", "drift_metrics.json"),
]
PARSE_SUCCESS_TARGET = 0.95


def read_json(path: Path) -> Optional[Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_csv(path: Path) -> List[Dict[str, Any]]:
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def stage_state(name: str, m: Optional[dict]) -> str:
    if m is None:
        return "missing"
    if name == "download" and m.get("filings_failed", 0) > 0:
        return "warning"
    if name == "parse" and m.get("success_rate", 1.0) < PARSE_SUCCESS_TARGET:
        return "warning"
    if name == "drift" and m.get("drift_detected", 0) == 1:
        return "warning"
    if name == "prices" and (m.get("symbols_missing", 0) + m.get("symbols_sparse", 0)) > 0:
        return "warning"
    return "ok"


def read_events(reports_dir: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Pipeline event log (reports/run_history.jsonl), newest first. Bad lines are skipped."""
    try:
        lines = (Path(reports_dir) / "run_history.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events: List[Dict[str, Any]] = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    events.reverse()
    return events[:limit] if limit else events


def _mtime(path: Path) -> Optional[str]:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def collect(reports_dir: str) -> Dict[str, Any]:
    base = Path(reports_dir)
    stages = []
    for name, fname in STAGES:
        m = read_json(base / fname)
        stages.append(
            {"name": name, "status": stage_state(name, m), "updated_at": _mtime(base / fname), "metrics": m or {}}
        )
    return {
        "stages": stages,
        "model_comparison": read_csv(base / "model_comparison.csv"),
        "test_uncertainty": read_csv(base / "test_uncertainty.csv"),
        "ray_benchmark": read_json(base / "ray_benchmark.json") or [],
        "parse_failure_count": len(read_csv(base / "parse_failures.csv")),
        "drift_report": read_json(base / "drift_report.json"),
        "events": read_events(reports_dir, limit=20),
    }
