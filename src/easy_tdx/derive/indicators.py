"""技术指标（纯计算，口径对齐通达信）。

- MA / EMA
- MACD（DIF/DEA/MACD，MACD 柱 = 2×(DIF−DEA)）
- KDJ（RSV → K/D 用 SMA(x, n, 1) 平滑，J = 3K−2D）
- BOLL（MA ± k×估算标准差/样本，通达信语义）
- RSI（SMA(涨, n, 1) / SMA(|Δ|, n, 1) × 100）
- 量比（当日量 / 近 N 日均量）

所有函数接收/返回 ``pandas`` 对象，无网络依赖。
"""

from __future__ import annotations

import pandas as pd

__all__ = [
    "ma",
    "ema",
    "macd",
    "kdj",
    "boll",
    "rsi",
    "volume_ratio",
    "add_indicators",
]


def ma(series: pd.Series, periods: int | list[int] = 20) -> pd.Series | pd.DataFrame:
    """简单移动平均。"""
    if isinstance(periods, int):
        return series.rolling(periods).mean()
    return pd.DataFrame({f"ma{p}": series.rolling(p).mean() for p in periods})


def ema(series: pd.Series, span: int) -> pd.Series:
    """指数移动平均（alpha = 2/(span+1)）。"""
    return series.ewm(span=span, adjust=False).mean()


def _sma_cn(series: pd.Series, n: int) -> pd.Series:
    """通达信 SMA(x, n, 1)：等价于 alpha = 1/n 的指数平滑。"""
    return series.ewm(alpha=1.0 / n, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD。返回列：dif、dea、macd。"""
    dif = ema(close, fast) - ema(close, slow)
    dea = ema(dif, signal)
    return pd.DataFrame({"dif": dif, "dea": dea, "macd": (dif - dea) * 2})


def kdj(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    n: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> pd.DataFrame:
    """KDJ。返回列：k、d、j。"""
    lowest = low.rolling(n).min()
    highest = high.rolling(n).max()
    span = (highest - lowest).replace(0, pd.NA)
    rsv = ((close - lowest) / span * 100).fillna(50.0)
    k = _sma_cn(rsv, k_period)
    d = _sma_cn(k, d_period)
    return pd.DataFrame({"k": k, "d": d, "j": 3 * k - 2 * d})


def boll(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    """布林带。返回列：boll_upper、boll_mid、boll_lower。"""
    mid = close.rolling(n).mean()
    std = close.rolling(n).std(ddof=1)
    return pd.DataFrame({"boll_upper": mid + k * std, "boll_mid": mid, "boll_lower": mid - k * std})


def rsi(
    close: pd.Series, periods: int | list[int] | tuple[int, ...] = (6, 12, 24)
) -> pd.Series | pd.DataFrame:
    """RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    absd = delta.abs()

    def _one(n: int) -> pd.Series:
        up = _sma_cn(gain, n)
        total = _sma_cn(absd, n)
        return (up / total.replace(0, pd.NA) * 100).fillna(0.0)

    if isinstance(periods, int):
        return _one(periods)
    return pd.DataFrame({f"rsi{p}": _one(p) for p in periods})


def volume_ratio(vol: pd.Series, period: int = 5) -> pd.Series:
    """量比 = 当日成交量 / 近 period 日均量。"""
    return vol / vol.rolling(period).mean()


def add_indicators(
    bars: pd.DataFrame,
    *,
    ma_periods: list[int] | None = None,
    macd_params: tuple[int, int, int] = (12, 26, 9),
    kdj_params: tuple[int, int, int] = (9, 3, 3),
    boll_params: tuple[int, float] = (20, 2.0),
    rsi_periods: list[int] | None = None,
    volume_ratio_period: int | None = 5,
) -> pd.DataFrame:
    """在日线 DataFrame 上追加常用指标列（不修改原对象）。"""
    df = bars.copy()
    close = df["close"]
    if ma_periods:
        df = df.join(ma(close, ma_periods))
    df = df.join(macd(close, *macd_params))
    if {"high", "low"} <= set(df.columns):
        df = df.join(kdj(df["high"], df["low"], close, *kdj_params))
    df = df.join(boll(close, *boll_params))
    if rsi_periods:
        df = df.join(rsi(close, rsi_periods))
    if volume_ratio_period and "vol" in df.columns:
        df["volume_ratio"] = volume_ratio(df["vol"], volume_ratio_period)
    return df
