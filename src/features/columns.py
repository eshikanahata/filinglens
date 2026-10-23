"""Single source of truth for model feature names and their order."""

FEATURE_COLUMNS = [
    "neg_ratio",
    "unc_ratio",
    "lit_ratio",
    "pos_ratio",  # Loughran-McDonald word shares
    "fk_grade",
    "avg_sentence_len",  # readability
    "log_risk_words",
    "risk_share",  # length
    "risk_words_change",
    "tfidf_similarity",  # year-over-year text change
    "d_neg_ratio",
    "d_unc_ratio",
    "d_lit_ratio",
    "d_fk_grade",  # year-over-year deltas
]
