from api.explain import build_reasons, signal_label


def test_signal_labels():
    assert signal_label(None, 0.6, 0.4) == "Not enough data"
    assert signal_label(0.7, 0.6, 0.4) == "Elevated"
    assert signal_label(0.6, 0.6, 0.4) == "Elevated"
    assert signal_label(0.5, 0.6, 0.4) == "Moderate"
    assert signal_label(0.3, 0.6, 0.4) == "Lower"


def test_reasons_pick_unusual_changes_most_extreme_first():
    feats = {
        "risk_words_change": 0.30,
        "tfidf_similarity": 0.62,
        "d_unc_ratio": 0.004,
        "d_neg_ratio": 0.0001,
        "d_lit_ratio": 0.0,
        "d_fk_grade": 0.2,
    }
    pcts = {
        "risk_words_change": 85.0,
        "tfidf_similarity": 4.0,
        "d_unc_ratio": 91.0,
        "d_neg_ratio": 55.0,
        "d_lit_ratio": 50.0,
        "d_fk_grade": 60.0,
    }
    out = build_reasons(feats, pcts)
    assert len(out) == 3  # the three unusual ones only
    assert "62%" in out[0] and "lower than 96%" in out[0]  # most extreme: similarity at 4th pct
    assert any("grew 30%" in r for r in out)
    assert any("uncertainty" in r and "rose" in r for r in out)


def test_reasons_fallback_when_nothing_unusual():
    feats = {"risk_words_change": 0.01, "tfidf_similarity": 0.9}
    pcts = {"risk_words_change": 50.0, "tfidf_similarity": 55.0}
    assert "Nothing stands out" in build_reasons(feats, pcts)[0]


def test_reasons_capped_at_four():
    feats = {
        k: 0.1
        for k in ("risk_words_change", "tfidf_similarity", "d_neg_ratio", "d_unc_ratio", "d_lit_ratio", "d_fk_grade")
    }
    pcts = {k: 95.0 for k in feats}
    assert len(build_reasons(feats, pcts)) == 4


def test_statements_never_contain_nested_parentheses():
    feats = {
        k: 0.1
        for k in ("risk_words_change", "tfidf_similarity", "d_neg_ratio", "d_unc_ratio", "d_lit_ratio", "d_fk_grade")
    }
    pcts = {**{k: 95.0 for k in feats}, "d_fk_grade": 10.0}
    for statement in build_reasons({**feats, "d_fk_grade": -0.2}, pcts) + build_reasons(
        feats, {**pcts, "d_fk_grade": 99.0}
    ):
        assert statement.count("(") == 1 and statement.count(")") == 1, statement
