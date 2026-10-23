"""Pure text-metric functions (no I/O except the dictionary loader)."""

import re
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd

WORD_RE = re.compile(r"[A-Za-z]+")
SENT_RE = re.compile(r"[.!?]+(?:\s|$)")
LM_COLUMNS = {"neg": "Negative", "pos": "Positive", "unc": "Uncertainty", "lit": "Litigious"}

MISSING_DICT_MSG = (
    "Loughran-McDonald dictionary not found at {path}. Download the Master Dictionary "
    "CSV from the Notre Dame SRAF site (sraf.nd.edu, free for academic use), save it "
    "there, then run `dvc add` on it."
)


def tokenize(text: str) -> List[str]:
    """Upper-case alphabetic tokens."""
    return [w.upper() for w in WORD_RE.findall(text)]


def load_lm_dictionary(path: str) -> Dict[str, Set[str]]:
    """Word sets per sentiment category from the LM master dictionary CSV.

    In that file a category column holds the year a word was added, or 0 when
    the word is not in the category, so `> 0` means membership.
    """
    if not Path(path).exists():
        raise FileNotFoundError(MISSING_DICT_MSG.format(path=path))
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    needed = ["Word"] + list(LM_COLUMNS.values())
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError(f"LM dictionary is missing columns: {missing}")
    words = df["Word"].astype(str).str.upper()
    out: Dict[str, Set[str]] = {}
    for key, col in LM_COLUMNS.items():
        flag = pd.to_numeric(df[col], errors="coerce").fillna(0) > 0
        out[key] = set(words[flag])
    return out


def lm_ratios(tokens: List[str], lm: Dict[str, Set[str]]) -> Dict[str, float]:
    """Share of tokens in each LM category."""
    n = max(len(tokens), 1)
    return {f"{k}_ratio": sum(1 for t in tokens if t in words) / n for k, words in lm.items()}


def count_syllables(word: str) -> int:
    """Rough English syllable estimate (vowel groups, minus a silent final e)."""
    w = word.lower()
    count = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and not w.endswith("le") and count > 1:
        count -= 1
    return max(count, 1)


def readability(text: str, tokens: List[str]) -> Dict[str, float]:
    """Flesch-Kincaid grade level and average sentence length."""
    words = max(len(tokens), 1)
    sentences = max(len(SENT_RE.findall(text)), 1)
    syllables = sum(count_syllables(t) for t in tokens)
    return {
        "fk_grade": 0.39 * words / sentences + 11.8 * syllables / words - 15.59,
        "avg_sentence_len": words / sentences,
    }
