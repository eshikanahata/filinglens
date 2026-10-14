import csv
import json

import pytest

pytest.importorskip("ray")

from src.parsing.parse_filings import run_parsing  # noqa: E402
from tests.test_section_extractor import make_html  # noqa: E402


def test_ray_parse_end_to_end(tmp_path):
    raw = tmp_path / "raw"
    rows = []
    for i, good in enumerate([True, True, False]):
        p = raw / "TST" / f"acc{i}.htm"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(make_html() if good else b"<html><body>broken</body></html>")
        rows.append({"ticker": "TST", "accession": f"acc{i}", "filing_date": "2023-01-01",
                     "report_date": "2022-12-31", "path": str(p), "status": "downloaded"})
    manifest = tmp_path / "manifest.csv"
    with open(manifest, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    out = tmp_path / "parsed"
    m = run_parsing(manifest, out, workers=2, min_chars=3000)
    assert m["filings_total"] == 3 and m["filings_ok"] == 2 and m["filings_failed"] == 1
    assert len(m["failures"]) == 1 and "SectionNotFoundError" in m["failures"][0]["error"]
    rec = json.loads((out / "TST" / "acc0.json").read_text())
    assert rec["risk_words"] > 500
