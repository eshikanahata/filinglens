import numpy as np
import pandas as pd
import pytest

from src.serving.build_serving_data import percentile_table, top_term_changes


def test_percentiles_only_among_filings_with_prior():
    df = pd.DataFrame({"has_prior": [False, True, True, True], "tfidf_similarity": [np.nan, 0.6, 0.8, 0.9]})
    out = percentile_table(df, ["tfidf_similarity"])
    assert list(out.index) == [1, 2, 3]
    assert out["tfidf_similarity"].tolist() == pytest.approx([100 / 3, 200 / 3, 100.0])


def test_top_term_changes():
    names = np.array(["cyber", "covid", "tax", "labor"])
    cur = np.array([0.5, 0.0, 0.2, 0.1])
    prior = np.array([0.1, 0.4, 0.2, 0.1])
    up, down = top_term_changes(cur, prior, names, k=3)
    assert up == ["cyber"]  # only strictly increased terms are reported
    assert down == ["covid"]
