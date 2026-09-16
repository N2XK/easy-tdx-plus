"""通达信公式解释器测试（离线，手工核对）。"""

from __future__ import annotations

import numpy as np
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
    assert out["V"].iloc[-1] == pytest.approx(pd.Series([15.0, 16.0, 15.0]).var(ddof=1))


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
    # STDDEV 保留总体标准差（ddof=0）语义
    pd.testing.assert_series_equal(
        out["S"], bars["close"].rolling(3).std(ddof=0), check_names=False
    )


def _swing_bars() -> pd.DataFrame:
    close = [10.0, 12.0, 8.0, 12.0, 8.0, 13.0, 7.0]
    return pd.DataFrame({"close": close, "high": close, "low": close, "vol": [1.0] * 7})


def test_zig_and_swings() -> None:
    out = evaluate(
        "Z: ZIG(CLOSE,10); P: PEAK(CLOSE,10,1); T: TROUGH(CLOSE,10,1); "
        "PB: PEAKBARS(CLOSE,10,1); TB: TROUGHBARS(CLOSE,10,1);",
        _swing_bars(),
    )
    assert pd.isna(out["Z"].iloc[0])
    assert out["Z"].tolist()[1:] == [12.0, 8.0, 12.0, 8.0, 13.0, 13.0]
    assert out["P"].iloc[1] == 12.0 and out["P"].iloc[5] == 13.0
    assert out["T"].iloc[4] == 8.0
    assert out["PB"].iloc[6] == 1.0
    assert out["TB"].iloc[6] == 2.0


def test_peak_m_back() -> None:
    out = evaluate("P2: PEAK(CLOSE,10,2);", _swing_bars())
    assert out["P2"].iloc[3] == 12.0
    assert out["P2"].iloc[5] == 12.0


def _long_bars(n: int = 40) -> pd.DataFrame:
    close = [10 + (i % 7) + (i % 3) * 0.5 for i in range(n)]
    return pd.DataFrame(
        {
            "open": close,
            "high": [c + 1 for c in close],
            "low": [c - 0.5 for c in close],
            "close": close,
            "vol": [100.0 + i for i in range(n)],
        }
    )


def test_macd_matches_indicator() -> None:
    from easy_tdx.derive import macd as ind_macd

    bars = _long_bars()
    out = evaluate("DIF: EMA(CLOSE,12)-EMA(CLOSE,26); DEA: EMA(DIF,9); M: (DIF-DEA)*2;", bars)
    expect = ind_macd(bars["close"])
    pd.testing.assert_series_equal(out["DIF"], expect["dif"], check_names=False)
    pd.testing.assert_series_equal(out["DEA"], expect["dea"], check_names=False)
    pd.testing.assert_series_equal(out["M"], expect["macd"], check_names=False)


def test_kdj_matches_indicator() -> None:
    from easy_tdx.derive import kdj as ind_kdj

    bars = _long_bars()
    out = evaluate(
        "RSV:= (CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100; "
        "K: SMA(RSV,3,1); D: SMA(K,3,1); J: 3*K-2*D;",
        bars,
    )
    expect = ind_kdj(bars["high"], bars["low"], bars["close"])
    for col, key in (("K", "k"), ("D", "d"), ("J", "j")):
        assert np.allclose(
            out[col].iloc[36:].to_numpy(),
            expect[key].iloc[36:].to_numpy(),
            rtol=1e-4,
            atol=1e-3,
        )


def test_boll_matches_indicator() -> None:
    from easy_tdx.derive import boll as ind_boll

    bars = _long_bars()
    out = evaluate("MID: MA(CLOSE,20); UP: MID+2*STD(CLOSE,20); LO: MID-2*STD(CLOSE,20);", bars)
    expect = ind_boll(bars["close"])
    pd.testing.assert_series_equal(out["MID"], expect["boll_mid"], check_names=False)
    pd.testing.assert_series_equal(out["UP"], expect["boll_upper"], check_names=False)
    pd.testing.assert_series_equal(out["LO"], expect["boll_lower"], check_names=False)


def test_obv() -> None:
    close = [10.0, 11.0, 10.0, 12.0, 12.0]
    bars = pd.DataFrame(
        {"close": close, "vol": [1.0, 2.0, 3.0, 4.0, 5.0], "high": close, "low": close}
    )
    out = evaluate("O: OBV();", bars)
    assert out["O"].tolist() == [0.0, 2.0, -1.0, 3.0, 3.0]


def test_tr_and_atr() -> None:
    bars = _bars()
    out = evaluate("T: TR(); A: ATR(2);", bars)
    close = bars["close"].tolist()
    assert out["T"].iloc[0] == pytest.approx(2.0)  # high-low = (c+1)-(c-1)
    prev = close[0]
    assert out["T"].iloc[1] == pytest.approx(max(2.0, abs(11 + 1 - prev), abs(11 - 1 - prev)))
    assert pd.isna(out["A"].iloc[0])
    assert out["A"].iloc[1] == pytest.approx((out["T"].iloc[0] + out["T"].iloc[1]) / 2)


def test_dmi_family() -> None:
    bars = _long_bars()
    out = evaluate("P: PDI(14); M: MDI(14); A: ADX(14); R: ADXR(14);", bars)
    for col in ("P", "M", "A"):
        vals = out[col].iloc[14:]
        assert (vals >= 0).all() and (vals <= 100).all()
    assert out["R"].iloc[-1] == pytest.approx((out["A"].iloc[-1] + out["A"].iloc[-15]) / 2)


def test_sar_structural() -> None:
    bars = _long_bars()
    out = evaluate("S: SAR(4,2,20);", bars)
    s = out["S"]
    assert s.iloc[0] == bars["low"].iloc[0]
    assert s.iloc[1:].notna().all()


def test_wma_mtm_roc_dpo() -> None:
    bars = _long_bars()
    out = evaluate("W: WMA(CLOSE,3); M: MTM(CLOSE,2); R: ROC(CLOSE,2); D: DPO(CLOSE,4);", bars)
    close = bars["close"]
    w = close.rolling(3).apply(lambda x: (x * [1, 2, 3]).sum() / 6.0, raw=True)
    pd.testing.assert_series_equal(out["W"], w, check_names=False)
    pd.testing.assert_series_equal(out["M"], close - close.shift(2), check_names=False)
    expect_r = (close / close.shift(2) - 1) * 100
    pd.testing.assert_series_equal(
        out["R"].dropna().reset_index(drop=True),
        expect_r.dropna().reset_index(drop=True),
        check_names=False,
    )
    ma = close.rolling(4).mean()
    pd.testing.assert_series_equal(out["D"], close - ma.shift(3), check_names=False)


def test_std_var_are_sample_and_stdp_varp_population() -> None:
    """通达信语义：STD/VAR 为样本(ddof=1)，STDP/VARP 为总体(ddof=0)。"""
    bars = _bars()
    close = bars["close"]
    out = evaluate("A: STD(CLOSE,5); B: STDP(CLOSE,5); C: VAR(CLOSE,5); D: VARP(CLOSE,5);", bars)
    pd.testing.assert_series_equal(out["A"], close.rolling(5).std(ddof=1), check_names=False)
    pd.testing.assert_series_equal(out["B"], close.rolling(5).std(ddof=0), check_names=False)
    pd.testing.assert_series_equal(out["C"], close.rolling(5).var(ddof=1), check_names=False)
    pd.testing.assert_series_equal(out["D"], close.rolling(5).var(ddof=0), check_names=False)


def test_zero_period_means_cumulative() -> None:
    """通达信语义：N=0 时 SUM/HHV/LLV/COUNT 从第一个有效值开始累计。"""
    bars = _bars()
    out = evaluate("S: SUM(CLOSE,0); H: HHV(HIGH,0); L: LLV(LOW,0); C: COUNT(CLOSE>11,0);", bars)
    close = bars["close"]
    assert out["S"].tolist() == pytest.approx(close.expanding().sum().tolist())
    assert out["H"].tolist() == pytest.approx(bars["high"].expanding().max().tolist())
    assert out["L"].tolist() == pytest.approx(bars["low"].expanding().min().tolist())
    assert out["C"].iloc[-1] == float((close > 11).sum())


def test_newly_added_functions() -> None:
    """DIFF/AVEDEV/EVERY/EXIST/VALUEWHEN/FORCAST/LAST/BARSSINCEN/LONGCROSS/TOPRANGE/LOWRANGE/三角函数。"""
    bars = _bars()
    close = bars["close"]
    out = evaluate(
        "A: DIFF(CLOSE,1); B: AVEDEV(CLOSE,3); C: EVERY(CLOSE>REF(CLOSE,1),3); "
        "D: EXIST(CLOSE>REF(CLOSE,1),3); E: VALUEWHEN(CLOSE>12,CLOSE); F: SIN(CLOSE);",
        bars,
    )
    assert out["A"].tolist() == pytest.approx(close.diff().tolist(), nan_ok=True)
    assert out["B"].iloc[-1] == pytest.approx(
        float((close.iloc[-3:].abs() - 0).add(0).pipe(lambda s: s).mean()) * 0
        + float((close.iloc[-3:] - close.iloc[-3:].mean()).abs().mean())
    )
    up = close > close.shift(1)
    assert out["C"].tolist() == [float(x) for x in (up.rolling(3).sum() == 3)]
    assert out["D"].tolist() == [float(x) for x in (up.rolling(3).sum() > 0)]
    assert out["E"].iloc[-1] == pytest.approx(float(close.iloc[-1]))
    assert out["F"].iloc[-1] == pytest.approx(np.sin(float(close.iloc[-1])))

    out2 = evaluate(
        "G: FORCAST(CLOSE,3); H: LAST(CLOSE>REF(CLOSE,1),2,1); "
        "I: TOPRANGE(HIGH); J: LOWRANGE(LOW); K: LONGCROSS(MA(CLOSE,2),MA(CLOSE,3),2);",
        bars,
    )
    # FORCAST 末值等于对最后 3 点做一次线性回归的端点预测
    y = close.iloc[-3:].to_numpy(dtype=float)
    assert out2["G"].iloc[-1] == pytest.approx(float(np.polyval(np.polyfit(range(3), y, 1), 2)))
    assert set(out2["H"].dropna().unique()) <= {0.0, 1.0}
    assert set(out2["I"].dropna().unique()) <= set(range(len(bars)))
    assert set(out2["J"].dropna().unique()) <= set(range(len(bars)))
    assert set(out2["K"].dropna().unique()) <= {0.0, 1.0}
