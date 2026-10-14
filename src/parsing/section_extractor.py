"""HTML -> clean text -> Item 1A (Risk Factors) section.

The hard part: "Item 1A. Risk Factors" appears in the table of contents, in
cross-references, and as the real heading. We collect every start marker and
every end marker (Item 1B / 1C / Item 2). Each start is paired with the first
end marker after it; spans shorter than `min_chars` (the TOC) are dropped, and
the longest remaining span wins.
"""
import re
from typing import List

from bs4 import BeautifulSoup

# Separators allowed between "Item 1A" and "Risk Factors". Commas and quotes are
# deliberately excluded so prose like: see Item 1A, "Risk Factors" is not matched.
_SEP = r"[\s.:\-\u2013\u2014]*"
START_RE = re.compile(rf"item\s*1a{_SEP}risk\s*factors", re.IGNORECASE)
END_RES = [
    re.compile(rf"item\s*1b{_SEP}unresolved\s*staff\s*comments", re.IGNORECASE),
    re.compile(rf"item\s*1c{_SEP}cybersecurity", re.IGNORECASE),
    re.compile(rf"item\s*2{_SEP}properties", re.IGNORECASE),
]


class SectionNotFoundError(Exception):
    """The Risk Factors section could not be located."""


def html_to_text(html: bytes) -> str:
    """Strip markup and hidden inline-XBRL header; collapse whitespace."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text(separator=" ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_risk_section(text: str, min_chars: int = 3000) -> str:
    """Return the Item 1A text, or raise SectionNotFoundError."""
    starts: List[int] = [m.start() for m in START_RE.finditer(text)]
    ends: List[int] = sorted(m.start() for rx in END_RES for m in rx.finditer(text))
    if not starts:
        raise SectionNotFoundError("no 'Item 1A. Risk Factors' marker found")
    if not ends:
        raise SectionNotFoundError("no end marker (Item 1B/1C/2) found")

    # Pair each start with the FIRST end marker after it (so the section stops at
    # Item 1B, not at a later Item 2). If several starts share an end marker, keep
    # the latest one that still leaves min_chars; this drops cross-references that
    # appear earlier in Item 1.
    chosen = {}
    for s in starts:
        e = next((e for e in ends if e > s), None)
        if e is None or e - s < min_chars:
            continue
        chosen[e] = max(chosen.get(e, -1), s)

    best = ""
    for e, s in chosen.items():
        candidate = text[s:e].strip()
        if len(candidate) > len(best):
            best = candidate
    if not best:
        raise SectionNotFoundError(
            f"no Item 1A span of at least {min_chars} characters (TOC hit only?)"
        )
    return best
