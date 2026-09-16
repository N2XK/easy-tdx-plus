"""技术指标测试（离线，手工核对）。"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx import add_indicators, boll, ema, kdj, ma, macd, rsi, volume_ratio


def test_ma() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ma(s, 2)
    assert pd.isna(out.iloc[0])
    assert out.iloc[1:].tolist() == pytest.approx([1.5, 2.5, 3.5, 4.5])
    multi = ma(s, [2, 3])
    assert list(multi.columns) == ["ma2", "ma3"]
    assert multi["ma3"].iloc[2] == pytest.approx(2.0)


def test_ema() -> None:
    out = ema(pd.Series([1.0, 2.0, 3.0]), span=3)
    assert out.tolist() == pytest.approx([1.0, 1.5, 2.25])


def test_macd_constant_is_zero() -> None:
    out = macd(pd.Series([10.0] * 40))
    assert out["dif"].abs().max() == pytest.approx(0.0)
    assert out["macd"].abs().max() == pytest.approx(0.0)


def test_macd_uptrend_positive_dif() -> None:
    out = macd(pd.Series(range(1, 60), dtype=float))
    assert out["dif"].iloc[-1] > 0


def test_kdj_flat_is_50() -> None:
    flat = pd.Series([10.0] * 20)
    out = kdj(flat, flat, flat, n=9)
    assert out["k"].iloc[-1] == pytest.approx(50.0)
    assert out["d"].iloc[-1] == pytest.approx(50.0)
    assert out["j"].iloc[-1] == pytest.approx(50.0)


def test_kdj_uptrend_j_high() -> None:
    close = pd.Series(range(1, 30), dtype=float)
    out = kdj(close + 1, close - 1, close, n=9)
    assert out["k"].iloc[-1] > 80


def test_boll_constant_band_collapses() -> None:
    out = boll(pd.Series([5.0] * 25), n=20, k=2.0)
    last = out.iloc[-1]
    assert last["boll_mid"] == pytest.approx(5.0)
    assert last["boll_upper"] == pytest.approx(5.0)
    assert last["boll_lower"] == pytest.approx(5.0)


def test_boll_band_width() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    out = boll(s, n=5, k=2.0)
    last = out.iloc[-1]
    # 估算（样本）标准差 ddof=1 -> sqrt(2) * sqrt(5/4) = sqrt(2.5)（通达信 BOLL 语义）
    sample_std = (2.0**0.5) * (5 / 4) ** 0.5
    assert last["boll_upper"] == pytest.approx(3.0 + 2 * sample_std)
    assert last["boll_lower"] == pytest.approx(3.0 - 2 * sample_std)


def test_rsi_uptrend_is_100() -> None:
    out = rsi(pd.Series(range(1, 40), dtype=float), 6)
    assert out.iloc[-1] == pytest.approx(100.0)


def test_rsi_flat_is_zero() -> None:
    out = rsi(pd.Series([7.0] * 30), 6)
    assert out.iloc[-1] == pytest.approx(0.0)


def test_rsi_multi_periods() -> None:
    out = rsi(pd.Series(range(1, 40), dtype=float), [6, 12])
    assert list(out.columns) == ["rsi6", "rsi12"]


def test_volume_ratio() -> None:
    out = volume_ratio(pd.Series([10.0, 10.0, 10.0, 20.0]), period=3)
    assert out.iloc[-1] == pytest.approx(20.0 / (40.0 / 3))


def test_add_indicators() -> None:
    n = 30
    bars = pd.DataFrame(
        {
            "close": [float(i) for i in range(1, n + 1)],
            "high": [float(i) + 1 for i in range(1, n + 1)],
            "low": [float(i) - 1 for i in range(1, n + 1)],
            "vol": [100.0] * n,
        }
    )
    out = add_indicators(bars, ma_periods=[5, 10], rsi_periods=[6])
    for col in ("ma5", "dif", "dea", "macd", "k", "d", "j", "boll_mid", "rsi6", "volume_ratio"):
        assert col in out.columns
    assert "ma5" not in bars.columns  # 不修改原对象
