import pytest

from src.parsing.section_extractor import (
    SectionNotFoundError,
    extract_risk_section,
    html_to_text,
)

BODY = "We face competition and regulatory uncertainty. " * 120  # ~5.7k chars


def make_html(toc=True, with_section=True, cross_ref=True):
    parts = ["<html><body>"]
    if toc:
        parts.append("<p>Item 1A. Risk Factors 12</p><p>Item 1B. Unresolved Staff Comments 30</p>")
    if cross_ref:
        parts.append(
            "<p>Our business is described below. See Item 1A. Risk Factors for more. "
            + "Business overview text. " * 200
            + "</p>"
        )
    if with_section:
        parts.append(f"<h2>Item&nbsp;1A.&nbsp;Risk Factors</h2><p>{BODY}</p>")
    parts.append("<h2>Item 1B. Unresolved Staff Comments</h2><p>None.</p>")
    parts.append("<h2>Item 2. Properties</h2></body></html>")
    return "".join(parts).encode()


def test_extracts_real_section_not_toc():
    text = html_to_text(make_html())
    section = extract_risk_section(text, min_chars=3000)
    assert section.startswith("Item 1A")
    assert "competition and regulatory uncertainty" in section
    assert "Unresolved Staff Comments" not in section
    assert len(section) > 5000


def test_toc_only_raises():
    text = html_to_text(make_html(with_section=False, cross_ref=False))
    with pytest.raises(SectionNotFoundError):
        extract_risk_section(text, min_chars=3000)


def test_no_marker_raises():
    with pytest.raises(SectionNotFoundError):
        extract_risk_section("just some text without items", 3000)


def test_ix_header_removed():
    html = b"<html><body><ix:header>HIDDEN_XBRL</ix:header><p>visible</p></body></html>"
    text = html_to_text(html)
    assert "HIDDEN_XBRL" not in text and "visible" in text


def test_heading_split_across_inline_tags():
    html = (
        b"<html><body><p>Item 1A. Risk Factors 5</p><p>Item 1B. Unresolved Staff Comments 9</p>"
        b"<h2>ITEM 1A. RIS<span>K</span> FACTORS</h2><p>"
        + BODY.encode()
        + b"</p><h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2></body></html>"
    )
    section = extract_risk_section(html_to_text(html), min_chars=3000)
    assert "competition and regulatory uncertainty" in section
