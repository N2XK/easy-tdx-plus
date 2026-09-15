"""派生计算测试：复权因子 / 前收盘 / 换手率（离线、合成数据）。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from easy_tdx.derive import adjust_bars, compute_adjust_factors, compute_basic_daily
from easy_tdx.derive.adjust import compute_pre_close_series


@dataclass
class _Ev:
    category: int
    year: int
    month: int
    day: int
    fenhong: float | None = None
    songzhuangu: float | None = None
    peigu: float | None = None
    peigujia: float | None = None


def _bars(closes: list[float], dates: list[str] | None = None) -> pd.DataFrame:
    dates = dates or [f"2026-01-0{i + 1}" for i in range(len(closes))]
    c = closes
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "open": c,
            "high": [x + 1 for x in c],
            "low": [x - 1 for x in c],
            "close": c,
            "vol": [100.0] * len(c),
        }
    )


def test_pre_close_10_for_10() -> None:
    # 第 2 天 10 送 10（songzhuangu=1.0/股），前收盘应为 10/(1+1)=5
    bars = _bars([10.0, 5.0, 5.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, songzhuangu=1.0)]
    pre = compute_pre_close_series(bars, ev)
    assert pre.iloc[0] == 10.0
    assert pre.iloc[1] == 5.0
    assert pre.iloc[2] == 5.0  # 第 3 天前收盘 = 第 2 天收盘


def test_compute_adjust_factors() -> None:
    bars = _bars([10.0, 5.0, 5.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, songzhuangu=1.0)]
    f = compute_adjust_factors(bars, ev)
    assert f["hfq_factor"].tolist() == [1.0, 2.0, 2.0]
    assert f["qfq_factor"].tolist() == [0.5, 1.0, 1.0]


def test_adjust_bars_qfq_hfq() -> None:
    bars = _bars([10.0, 5.0, 5.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, songzhuangu=1.0)]
    qfq = adjust_bars(bars, ev, mode="qfq")
    assert qfq["close"].tolist() == [5.0, 5.0, 5.5]  # 最新=原始，历史下调
    hfq = adjust_bars(bars, ev, mode="hfq")
    assert hfq["close"].tolist() == [10.0, 10.0, 11.0]  # 最早=原始，后续上调


def test_adjust_bars_invalid_mode() -> None:
    with pytest.raises(ValueError):
        adjust_bars(_bars([1.0]), [], mode="bad")


def test_basic_daily_turnover_and_change() -> None:
    bars = _bars([10.0, 5.0, 5.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, songzhuangu=1.0)]
    df = compute_basic_daily(bars, ev, float_shares=1000.0, total_shares=2000.0)
    # 除权日涨跌幅按调整前收盘计算，应为 0%
    assert df["change_pct"].iloc[1] == 0.0
    assert df["pre_close"].iloc[1] == 5.0
    # 换手率 = vol / 流通股 * 100
    assert df["turnover_pct"].iloc[0] == pytest.approx(10.0)
    assert df["float_mv"].iloc[0] == pytest.approx(10.0 * 1000)
    assert df["total_mv"].iloc[0] == pytest.approx(10.0 * 2000)


def test_cash_dividend_pre_close() -> None:
    # 每股派 0.5 元：pre_close = 10 - 0.5 = 9.5
    bars = _bars([10.0, 9.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, fenhong=0.5)]
    pre = compute_pre_close_series(bars, ev)
    assert pre.iloc[1] == pytest.approx(9.5)


def test_non_category1_ignored() -> None:
    bars = _bars([10.0, 5.0])
    ev = [_Ev(category=5, year=2026, month=1, day=2, songzhuangu=1.0)]
    f = compute_adjust_factors(bars, ev)
    assert f["hfq_factor"].tolist() == [1.0, 1.0]
