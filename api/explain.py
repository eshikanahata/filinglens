"""Turn year-over-year changes into plain-English statements (descriptive, not causal).

Each statement compares this filing with the rest of the dataset using percentiles,
so "unusual" means "unusual relative to other filings here", not an absolute rule.
"""
from typing import Dict, List, Optional

HIGH, LOW = 80.0, 20.0
MAX_REASONS = 4


def signal_label(score: Optional[float], elevated: float, low: float) -> str:
    if score is None:
        return "Not enough data"
    if score >= elevated:
        return "Elevated"
    if score <= low:
        return "Lower"
    return "Moderate"


def _rank_phrase(pct: float) -> str:
    return f"higher than {pct:.0f}% of filings" if pct >= 50 else f"lower than {100 - pct:.0f}% of filings"


def build_reasons(feats: Dict[str, Optional[float]], pcts: Dict[str, Optional[float]]) -> List[str]:
    """Up to MAX_REASONS statements, most unusual first."""
    candidates = []

    def add(key: str, text: str) -> None:
        pct = pcts.get(key)
        if pct is None or LOW < pct < HIGH:
            return
        candidates.append((abs(pct - 50.0), f"{text} ({_rank_phrase(pct)} in this dataset)."))

    chg = feats.get("risk_words_change")
    if chg is not None:
        verb = "grew" if chg >= 0 else "shrank"
        add("risk_words_change", f"The risk-factors section {verb} {abs(chg):.0%} compared with last year")
    sim = feats.get("tfidf_similarity")
    if sim is not None:
        add("tfidf_similarity", f"The risk-factors wording is {sim:.0%} similar to last year")
    for key, label in (("d_neg_ratio", "negative-tone"), ("d_unc_ratio", "uncertainty"),
                       ("d_lit_ratio", "litigation-related")):
        d = feats.get(key)
        if d is not None:
            verb = "rose" if d >= 0 else "fell"
            add(key, f"The share of {label} words {verb} by {abs(d) * 100:.2f} percentage points")
    fk = feats.get("d_fk_grade")
    if fk is not None:
        verb = "harder" if fk >= 0 else "easier"
        add("d_fk_grade", f"The risk section became {verb} to read by {abs(fk):.1f} grade levels")

    candidates.sort(key=lambda c: c[0], reverse=True)
    reasons = [text for _, text in candidates[:MAX_REASONS]]
    return reasons or ["Nothing stands out: this filing changed no more than is typical "
                       "compared with other filings in this dataset."]
