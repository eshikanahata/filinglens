import numpy as np
import pandas as pd

from src.labels.make_labels import compute_label


def make_series(n=80, start="2024-01-02", growth=0.001):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(100 * (1 + growth) ** np.arange(n), index=idx)


def test_underperformer_gets_target_1():
    stock, bench = make_series(growth=0.0), make_series(growth=0.002)
    out = compute_label(stock, bench, "2024-01-10", horizon=30)
    assert out["labeled"] and out["target"] == 1 and out["abnormal_ret"] < 0


def test_outperformer_gets_target_0():
    stock, bench = make_series(growth=0.003), make_series(growth=0.001)
    assert compute_label(stock, bench, "2024-01-10", 30)["target"] == 0


def test_base_is_last_trading_day_on_or_before_filing():
    s = make_series()
    # 2024-01-13 is a Saturday -> base must be Friday 2024-01-12
    out = compute_label(s, s, "2024-01-13", 30)
    assert out["base_date"] == "2024-01-12"


def test_recent_filing_is_unlabeled():
    s = make_series(n=40)
    out = compute_label(s, s, "2024-02-20", 30)
    assert not out["labeled"] and "fewer than 30" in out["reason"]


def test_filing_before_price_history_is_unlabeled():
    s = make_series()
    assert not compute_label(s, s, "2023-06-01", 30)["labeled"]


def test_price_gap_is_unlabeled():
    s = make_series(n=80)
    gap = s.drop(s.index[5:20])  # a long hole in the data
    out = compute_label(gap, gap, "2024-01-25", 10)
    assert not out["labeled"] and "gap" in out["reason"]
