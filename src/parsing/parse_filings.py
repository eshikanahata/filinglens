"""DVC stage `parse`: raw 10-K HTML -> Risk Factors text + stats, using Ray.

Each filing is an independent task, so the work is embarrassingly parallel.
`run_parsing` is reused by the benchmark script to compare worker counts.
"""

import argparse
import csv
import json
import logging
import time
from pathlib import Path
from typing import Dict, List

import ray

from src.common.config import load_params, setup_logging
from src.parsing.section_extractor import extract_risk_section, html_to_text

logger = logging.getLogger(__name__)

MANIFEST = Path("data/raw/manifest.csv")
PARSED_DIR = Path("data/parsed")
METRICS = Path("reports/parse_metrics.json")
FAILURES = Path("reports/parse_failures.csv")


@ray.remote
def parse_one(task: Dict[str, str]) -> Dict[str, object]:
    """Parse a single filing. Never raises: failures are returned as data."""
    started = time.time()
    result: Dict[str, object] = {
        "ticker": task["ticker"],
        "accession": task["accession"],
        "status": "failed",
        "error": "",
        "risk_words": 0,
        "full_words": 0,
    }
    try:
        text = html_to_text(Path(task["path"]).read_bytes())
        risk = extract_risk_section(text, int(task["min_chars"]))
        record = {
            "ticker": task["ticker"],
            "accession": task["accession"],
            "filing_date": task["filing_date"],
            "report_date": task["report_date"],
            "risk_factors": risk,
            "risk_words": len(risk.split()),
            "full_words": len(text.split()),
        }
        out = Path(task["out_dir"]) / task["ticker"] / f"{task['accession']}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record), encoding="utf-8")
        result.update(status="ok", risk_words=record["risk_words"], full_words=record["full_words"])
    except Exception as exc:  # noqa: BLE001 - one bad filing must not stop the run
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["seconds"] = round(time.time() - started, 3)
    return result


def load_tasks(manifest: Path, out_dir: Path, min_chars: int) -> List[Dict[str, str]]:
    with open(manifest, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["status"] in ("downloaded", "skipped_existing")]
    return [{**r, "out_dir": str(out_dir), "min_chars": str(min_chars)} for r in rows]


def run_parsing(manifest: Path, out_dir: Path, workers: int, min_chars: int) -> Dict:
    """Parse every manifest entry with `workers` Ray workers; return metrics."""
    tasks = load_tasks(manifest, out_dir, min_chars)
    ray.init(num_cpus=workers, include_dashboard=False, logging_level=logging.WARNING, ignore_reinit_error=True)
    started = time.time()
    try:
        results = ray.get([parse_one.remote(t) for t in tasks])
    finally:
        ray.shutdown()
    elapsed = time.time() - started

    ok = sum(r["status"] == "ok" for r in results)
    total = len(results)
    metrics = {
        "workers": workers,
        "filings_total": total,
        "filings_ok": ok,
        "filings_failed": total - ok,
        "success_rate": round(ok / total, 4) if total else 0.0,
        "elapsed_seconds": round(elapsed, 2),
        "filings_per_minute": round(total / elapsed * 60, 1) if elapsed > 0 else 0.0,
        "failures": [r for r in results if r["status"] != "ok"],
    }
    return metrics


def write_reports(metrics: Dict, metrics_path: Path, failures_path: Path) -> None:
    failures = metrics.pop("failures")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2))
    with open(failures_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ticker", "accession", "error"])
        writer.writeheader()
        for f in failures:
            writer.writerow({k: f[k] for k in ("ticker", "accession", "error")})


def main() -> None:
    setup_logging("parse")
    params = load_params()["parsing"]
    cli = argparse.ArgumentParser()
    cli.add_argument("--workers", type=int, default=params["num_workers"])
    args = cli.parse_args()

    metrics = run_parsing(MANIFEST, PARSED_DIR, args.workers, params["min_section_chars"])
    logger.info(
        "Parsed %d/%d filings (%.1f%%) in %.1fs with %d worker(s)",
        metrics["filings_ok"],
        metrics["filings_total"],
        metrics["success_rate"] * 100,
        metrics["elapsed_seconds"],
        args.workers,
    )
    if metrics["success_rate"] < 0.95:
        logger.warning("Parse success below the 95%% acceptance target; see %s", FAILURES)
    write_reports(metrics, METRICS, FAILURES)


if __name__ == "__main__":
    main()
