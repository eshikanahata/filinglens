"""Summarise a pytest JUnit XML file per test module (for the Test Report).

    pytest -q --junitxml=reports/pytest_results.xml
    python scripts/summarize_tests.py
Writes reports/test_summary.json and reports/test_summary.md and prints the table.
"""
import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

XML = Path("reports/pytest_results.xml")


def summarise(xml_path: Path):
    modules = defaultdict(lambda: {"passed": 0, "failed": 0, "skipped": 0})
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        module = case.get("classname", "?").split(".")[-1] if "." in case.get("classname", "") else case.get("classname", "?")
        if case.find("failure") is not None or case.find("error") is not None:
            modules[module]["failed"] += 1
        elif case.find("skipped") is not None:
            modules[module]["skipped"] += 1
        else:
            modules[module]["passed"] += 1
    return dict(sorted(modules.items()))


def main() -> int:
    if not XML.exists():
        print(f"{XML} not found. Run: pytest -q --junitxml={XML}")
        return 2
    mods = summarise(XML)
    total = {k: sum(m[k] for m in mods.values()) for k in ("passed", "failed", "skipped")}
    total["total"] = sum(total.values())
    lines = ["| Test module | Passed | Failed | Skipped |", "|---|---|---|---|"]
    lines += [f"| {name} | {m['passed']} | {m['failed']} | {m['skipped']} |" for name, m in mods.items()]
    lines.append(f"| **Total ({total['total']})** | **{total['passed']}** | **{total['failed']}** | **{total['skipped']}** |")
    table = "\n".join(lines)
    Path("reports/test_summary.md").write_text(table + "\n")
    Path("reports/test_summary.json").write_text(json.dumps({"modules": mods, "total": total}, indent=2))
    print(table)
    return 0 if total["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
