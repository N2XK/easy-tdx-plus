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
    assert f["hfq_mul"].tolist() == [1.0, 2.0, 2.0]
    assert f["hfq_add"].tolist() == [0.0, 0.0, 0.0]
    assert f["qfq_mul"].tolist() == [0.5, 1.0, 1.0]
    assert f["qfq_add"].tolist() == [0.0, 0.0, 0.0]


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


def test_adjust_bars_cash_is_additive() -> None:
    """现金分红应为仿射减法（对齐通达信），而非乘法。"""
    bars = _bars([10.0, 9.5])
    ev = [_Ev(category=1, year=2026, month=1, day=2, fenhong=0.5)]
    qfq = adjust_bars(bars, ev, mode="qfq")
    assert qfq["close"].tolist() == [9.5, 9.5]  # 前复权：历史价 -0.5
    hfq = adjust_bars(bars, ev, mode="hfq")
    assert hfq["close"].tolist() == [10.0, 10.0]  # 后复权：后续价 +0.5


def test_non_category1_ignored() -> None:
    bars = _bars([10.0, 5.0])
    ev = [_Ev(category=5, year=2026, month=1, day=2, songzhuangu=1.0)]
    f = compute_adjust_factors(bars, ev)
    assert f["hfq_mul"].tolist() == [1.0, 1.0]


def test_get_fq_bars_hfq_window_invariant(monkeypatch) -> None:
    """hfq 因子必须基于全量历史计算：请求窗口改变不应改变同一日的后复权价。"""
    import pandas as pd

    from easy_tdx import Market, TdxClient

    dates = pd.date_range("2020-01-01", periods=6, freq="D")
    bars = pd.DataFrame(
        {
            "date": dates,
            "open": [10.0, 10.0, 5.0, 5.0, 5.0, 5.0],
            "high": [10.0, 10.0, 5.0, 5.0, 5.0, 5.0],
            "low": [10.0, 10.0, 5.0, 5.0, 5.0, 5.0],
            "close": [10.0, 10.0, 5.0, 5.0, 5.0, 5.0],
            "vol": [1.0] * 6,
        }
    )

    class _Ev:
        category = 1
        year, month, day = 2020, 1, 3
        fenhong, songzhuangu, peigu, peigujia = 0.0, 1.0, 0.0, 0.0

    calls: list[int] = []

    def fake_bars_with_xdxr(self, market, code, start_date, end_date):  # noqa: ANN001
        calls.append(start_date)
        return bars, [_Ev()]

    monkeypatch.setattr(TdxClient, "_daily_bars_with_xdxr", fake_bars_with_xdxr)
    c = TdxClient(host="127.0.0.1")

    full = c.get_fq_bars(Market.SZ, "000001", mode="hfq", start_date=19900101)
    part = c.get_fq_bars(Market.SZ, "000001", mode="hfq", start_date=20200104)
    # 因子始终取全量起点
    assert set(calls) == {19900101}
    # 输出按请求窗口裁剪，且重叠日期数值一致
    assert len(part) < len(full)
    d0 = pd.to_datetime(part["date"].iloc[0]).date()
    assert d0 >= pd.Timestamp("2020-01-04").date()
    merged = full.merge(part, on="date", suffixes=("_f", "_p"))
    assert len(merged) == len(part)
    assert (merged["close_f"] == merged["close_p"]).all()
