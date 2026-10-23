"""Measure API latency against the acceptance criterion (95th percentile under 1 second).

Needs the stack running (docker compose up -d). Sequential requests from the host, so the
numbers include loopback networking but no browser. Run:
    python scripts/measure_latency.py            # defaults: http://localhost:8000, 3 repeats
Writes reports/latency_report.json. Exit code 1 if the target is missed or any request fails.
"""

import argparse
import json
import math
import platform
import statistics
import time
from pathlib import Path
from typing import Dict, List

import requests

WARMUP = 5


def percentile(values: List[float], q: float) -> float:
    """Nearest-rank percentile (q in 0..1)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def timed_get(session: requests.Session, url: str):
    start = time.perf_counter()
    try:
        status = session.get(url, timeout=10).status_code
    except requests.RequestException:
        status = 0
    return status, time.perf_counter() - start


def summarise(samples: List[float], statuses: List[int]) -> Dict:
    ms = [s * 1000 for s in samples]
    return {
        "requests": len(ms),
        "errors": sum(1 for s in statuses if s == 0 or s >= 400),
        "p50_ms": round(statistics.median(ms), 1),
        "p95_ms": round(percentile(ms, 0.95), 1),
        "max_ms": round(max(ms), 1),
    }


def run(base: str, repeats: int) -> Dict:
    session = requests.Session()
    tickers = [t["ticker"] for t in session.get(f"{base}/tickers", timeout=10).json()["tickers"]]
    groups = {
        "GET /health": ["/health"] * (repeats * 10),
        "GET /tickers": ["/tickers"] * (repeats * 10),
        "GET /analysis/{ticker}": [f"/analysis/{t}" for t in tickers] * repeats,
        "GET /analysis/{ticker}/history": [f"/analysis/{t}/history" for t in tickers] * repeats,
        "GET /pipeline/runs": ["/pipeline/runs"] * (repeats * 10),
    }
    for path in ["/health", "/tickers", f"/analysis/{tickers[0]}"] * WARMUP:  # discarded warm-up
        timed_get(session, base + path)
    results = {}
    for name, paths in groups.items():
        samples, statuses = [], []
        for p in paths:
            status, secs = timed_get(session, base + p)
            samples.append(secs)
            statuses.append(status)
        results[name] = summarise(samples, statuses)
    return {
        "base_url": base,
        "companies": len(tickers),
        "repeats": repeats,
        "python": platform.python_version(),
        "machine": platform.platform(),
        "endpoints": results,
    }


def main() -> int:
    cli = argparse.ArgumentParser()
    cli.add_argument("--base", default="http://localhost:8000")
    cli.add_argument("--repeats", type=int, default=3)
    cli.add_argument("--target-ms", type=float, default=1000.0)
    cli.add_argument("--out", default="reports/latency_report.json")
    args = cli.parse_args()

    report = run(args.base.rstrip("/"), args.repeats)
    key = report["endpoints"]["GET /analysis/{ticker}"]
    report["target_ms"] = args.target_ms
    report["target_met"] = bool(
        key["p95_ms"] < args.target_ms and all(e["errors"] == 0 for e in report["endpoints"].values())
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))

    print(f"{'Endpoint':34s}{'requests':>9s}{'errors':>8s}{'p50 ms':>9s}{'p95 ms':>9s}{'max ms':>9s}")
    for name, e in report["endpoints"].items():
        print(f"{name:34s}{e['requests']:9d}{e['errors']:8d}{e['p50_ms']:9.1f}{e['p95_ms']:9.1f}{e['max_ms']:9.1f}")
    print(
        f"\nAcceptance: p95 of GET /analysis/{{ticker}} = {key['p95_ms']} ms "
        f"(target < {args.target_ms:.0f} ms) -> {'MET' if report['target_met'] else 'NOT MET'}"
    )
    return 0 if report["target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
