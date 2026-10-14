"""Diagnose why Item 1A extraction fails for one filing.
Usage: PYTHONPATH=. python scripts/diagnose_filing.py MSFT 0000950170-23-035122
"""
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from src.parsing.section_extractor import END_RES, START_RE, html_to_text

BLOCK = ["p", "div", "br", "tr", "td", "th", "li", "h1", "h2", "h3", "h4",
         "h5", "h6", "table"]


def html_to_text_blockaware(html: bytes) -> str:
    """Add whitespace only after block elements, so split words stay joined."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    for tag in soup.find_all(BLOCK):
        tag.insert_after(" ")
    text = soup.get_text(separator="")
    text = re.sub("[\u200b\u200c\u200d\ufeff\u00ad]", "", text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def show(label, pattern, text, limit=10):
    hits = list(re.finditer(pattern, text, re.I))
    print(f"  {label}: {len(hits)} hit(s)")
    for m in hits[:limit]:
        p = m.start()
        ctx = text[max(0, p - 50):p + 70]
        print(f"    @{p:>8,} ({p / len(text):5.1%})  {ctx!r}")


def report(label, text):
    starts = [m.start() for m in START_RE.finditer(text)]
    ends = sorted(m.start() for rx in END_RES for m in rx.finditer(text))
    print(f"\n=== {label}: {len(text):,} chars")
    print(f"  START_RE matches at: {starts}")
    print(f"  END_RES matches at:  {ends}")
    show("loose 'item 1a'", r"item\s*1\s*a", text)
    show("'risk factors'", r"risk\s*factors", text, limit=12)
    show("'unresolved staff'", r"unresolved\s*staff", text)


if __name__ == "__main__":
    ticker, acc = sys.argv[1], sys.argv[2]
    html = (Path("data/raw") / ticker / f"{acc}.htm").read_bytes()
    report("CURRENT extraction", html_to_text(html))
    report("BLOCK-AWARE extraction", html_to_text_blockaware(html))
