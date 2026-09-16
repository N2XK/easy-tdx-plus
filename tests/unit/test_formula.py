"""通达信公式解释器测试（离线，手工核对）。"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx import evaluate
from easy_tdx.derive import ema as ind_ema
from easy_tdx.derive import ma as ind_ma


def _bars() -> pd.DataFrame:
    close = [float(x) for x in [10, 11, 12, 11, 13, 14, 13, 15, 16, 15]]
    return pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 1 for c in close],
            "close": close,
            "vol": [100.0] * len(close),
        }
    )


def test_ma_matches_indicator() -> None:
    out = evaluate("MA5: MA(CLOSE,5);", _bars())
    assert list(out.columns) == ["MA5"]
    expect = ind_ma(_bars()["close"], 5)
    pd.testing.assert_series_equal(out["MA5"], expect, check_names=False)


def test_ema_matches_indicator() -> None:
    out = evaluate("E: EMA(CLOSE,3);", _bars())
    expect = ind_ema(_bars()["close"], 3)
    pd.testing.assert_series_equal(out["E"], expect, check_names=False)


def test_ref_and_arithmetic() -> None:
    out = evaluate("R: REF(CLOSE,1); F: CLOSE*2+1;", _bars())
    close = _bars()["close"]
    assert pd.isna(out["R"].iloc[0])
    assert out["R"].iloc[1:].tolist() == close.iloc[:-1].tolist()
    assert out["F"].tolist() == (close * 2 + 1).tolist()


def test_assignment_and_reuse() -> None:
    out = evaluate("M:=MA(CLOSE,2); D: CLOSE-M;", _bars())
    close = _bars()["close"]
    m = close.rolling(2).mean()
    assert out["D"].iloc[1:].tolist() == pytest.approx((close - m).iloc[1:].tolist())


def test_cross() -> None:
    out = evaluate("X: CROSS(MA(CLOSE,2), MA(CLOSE,4));", _bars())
    assert out["X"].dtype == bool


def test_if_hhv_llv() -> None:
    out = evaluate("H: HHV(HIGH,3); L: LLV(LOW,3); Y: IF(CLOSE>11,1,0);", _bars())
    hh = _bars()["high"].rolling(3).max()
    ll = _bars()["low"].rolling(3).min()
    pd.testing.assert_series_equal(out["H"], hh, check_names=False)
    pd.testing.assert_series_equal(out["L"], ll, check_names=False)
    assert out["Y"].iloc[-1] == 1.0


def test_logical_operators() -> None:
    out = evaluate("B: CLOSE>12 AND VOL>0;", _bars())
    assert out["B"].dtype == bool


def test_unknown_function_raises() -> None:
    from easy_tdx.derive import FormulaError

    with pytest.raises(FormulaError):
        evaluate("X: NOPE(CLOSE);", _bars())


def test_barslastcount_and_bars_count() -> None:
    bars = _bars()
    out = evaluate("A: BARSLASTCOUNT(CLOSE>11); N: BARSCOUNT(CLOSE);", bars)
    assert out["A"].tolist() == [0, 0, 1, 0, 1, 2, 3, 4, 5, 6]
    assert out["N"].tolist() == [float(i + 1) for i in range(len(bars))]


def test_hhvbars_llvbars() -> None:
    bars = _bars()
    out = evaluate("H: HHVBARS(HIGH,3); L: LLVBARS(LOW,3);", bars)
    hi = bars["high"].tolist()
    assert out["H"].iloc[2] == 0.0
    assert out["H"].iloc[3] == 1.0
    assert out["L"].iloc[1] == 1.0
    assert out["H"].iloc[5] == 0.0
    assert hi[5] == max(hi[3:6])


def test_backset() -> None:
    out = evaluate("B: BACKSET(CLOSE>14,3);", _bars())
    assert out["B"].tolist() == [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]


def test_sumbars() -> None:
    bars = _bars()
    out = evaluate("S: SUMBARS(VOL,250);", bars)
    assert out["S"][[0, 1, 2, 3]].tolist() == [1.0, 2.0, 3.0, 3.0]


def test_filter_and_tfilter_alias() -> None:
    out = evaluate("F: FILTER(CLOSE>11,2); T: TFILTER(CLOSE>11,2);", _bars())
    assert out["F"].tolist() == out["T"].tolist()
    assert out["F"].tolist() == [0, 0, 1, 0, 0, 1, 0, 0, 1, 0]


def test_upnday_downnday() -> None:
    bars = _bars()
    out = evaluate("U: UPNDAY(CLOSE,3); D: DOWNNDAY(CLOSE,2);", bars)
    assert out["U"].iloc[8] == 1.0
    assert out["U"].iloc[2] == 1.0
    assert out["D"].iloc[3] == 1.0
    assert out["D"].iloc[9] == 1.0


def test_slope_var_math() -> None:
    out = evaluate("S: SLOPE(CLOSE,2); V: VAR(CLOSE,3);", _bars())
    assert out["S"].iloc[-1] == pytest.approx(-1.0)
    assert out["V"].iloc[-1] == pytest.approx(pd.Series([15.0, 16.0, 15.0]).var(ddof=0))


def test_dma_and_const() -> None:
    bars = _bars()
    out = evaluate("D: DMA(CLOSE,0.5); C: CONST(CLOSE);", bars)
    close = bars["close"].tolist()
    assert out["D"].iloc[0] == close[0]
    assert out["D"].iloc[1] == pytest.approx(0.5 * close[1] + 0.5 * close[0])
    assert (out["C"] == close[-1]).all()


def test_math_builtins() -> None:
    out = evaluate(
        "A: SQRT(CLOSE); B: POW(CLOSE,2); "
        "C: INTPART(CLOSE/2); D: BETWEEN(CLOSE,11,13); E: SIGN(CLOSE-12);",
        _bars(),
    )
    assert out["A"].iloc[0] == pytest.approx(10**0.5)
    assert out["B"].iloc[0] == pytest.approx(100.0)
    assert out["C"].iloc[0] == 5.0
    assert out["D"].iloc[0] == 0.0 and out["D"].iloc[1] == 1.0
    assert out["E"].tolist() == [-1.0, -1.0, 0.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]


def test_aliases() -> None:
    bars = _bars()
    out = evaluate("A: IFF(CLOSE>11,1,0); B: AVERAGE(CLOSE,2); S: STDDEV(CLOSE,3);", bars)
    assert out["A"].dtype == float
    pd.testing.assert_series_equal(out["B"], ind_ma(bars["close"], 2), check_names=False)
    pd.testing.assert_series_equal(
        out["S"], bars["close"].rolling(3).std(ddof=0), check_names=False
    )
