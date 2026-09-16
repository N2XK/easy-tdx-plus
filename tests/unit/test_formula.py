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
