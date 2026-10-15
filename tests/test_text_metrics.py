import pytest

from src.features.text_metrics import (
    count_syllables, lm_ratios, load_lm_dictionary, readability, tokenize,
)

LM = {"neg": {"LOSS", "DECLINE"}, "pos": {"GAIN"}, "unc": {"MAY"}, "lit": {"LAWSUIT"}}


def test_tokenize_uppercases_alpha_only():
    assert tokenize("Loss of 25% in Q3, may decline.") == ["LOSS", "OF", "IN", "Q", "MAY", "DECLINE"]


def test_lm_ratios():
    toks = tokenize("loss loss may gain lawsuit text text text text")
    r = lm_ratios(toks, LM)
    assert r["neg_ratio"] == pytest.approx(2 / 9)
    assert r["unc_ratio"] == pytest.approx(1 / 9)
    assert r["lit_ratio"] == pytest.approx(1 / 9)


def test_lm_ratios_empty_text_is_safe():
    assert lm_ratios([], LM)["neg_ratio"] == 0


def test_syllables():
    assert count_syllables("cat") == 1
    assert count_syllables("table") == 2
    assert count_syllables("regulation") >= 3


def test_readability_harder_text_scores_higher():
    easy = "We sell food. We have cats. It is fun."
    hard = ("Notwithstanding considerable macroeconomic uncertainty, "
            "organizational restructuring necessitates substantial capitalization.")
    r_easy = readability(easy, tokenize(easy))
    r_hard = readability(hard, tokenize(hard))
    assert r_hard["fk_grade"] > r_easy["fk_grade"]


def test_load_lm_dictionary(tmp_path):
    p = tmp_path / "lm.csv"
    p.write_text("Word,Negative,Positive,Uncertainty,Litigious\n"
                 "LOSS,2009,0,0,0\nGAIN,0,2009,0,0\nMAY,0,0,2009,0\nSUE,0,0,0,2009\nTHE,0,0,0,0\n")
    lm = load_lm_dictionary(str(p))
    assert lm["neg"] == {"LOSS"} and lm["pos"] == {"GAIN"}
    assert lm["unc"] == {"MAY"} and lm["lit"] == {"SUE"}


def test_load_lm_dictionary_missing_file_has_helpful_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="SRAF"):
        load_lm_dictionary(str(tmp_path / "nope.csv"))


def test_load_lm_dictionary_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("Word,Negative\nLOSS,1\n")
    with pytest.raises(ValueError, match="missing columns"):
        load_lm_dictionary(str(p))
