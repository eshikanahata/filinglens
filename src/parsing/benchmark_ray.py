"""Ray throughput benchmark: parse the same filings with 1..N workers.

Writes reports/ray_benchmark.json. Run on its own (not a DVC stage) because it
writes throwaway output to tmp_benchmark/.
"""
import json
import logging
import shutil
from pathlib import Path

from src.common.config import load_params, setup_logging
from src.parsing.parse_filings import MANIFEST, run_parsing

logger = logging.getLogger(__name__)
OUT = Path("reports/ray_benchmark.json")
TMP = Path("tmp_benchmark")


def main(worker_counts=(1, 2, 4, 8)) -> None:
    setup_logging("benchmark")
    min_chars = load_params()["parsing"]["min_section_chars"]
    runs = []
    for w in worker_counts:
        logger.info("Starting run with %d worker(s)...", w)
        metrics = run_parsing(MANIFEST, TMP, w, min_chars)
        metrics.pop("failures")
        runs.append(metrics)
        logger.info("workers=%d -> %.1f filings/min", w, metrics["filings_per_minute"])
        shutil.rmtree(TMP, ignore_errors=True)
    base = runs[0]["filings_per_minute"] or 1.0
    for r in runs:
        r["speedup_vs_1_worker"] = round(r["filings_per_minute"] / base, 2)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(runs, indent=2))
    logger.info("Wrote %s", OUT)


if __name__ == "__main__":
    main()
