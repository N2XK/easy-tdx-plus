"""派生计算：复权（QFQ/HFQ）。

复权算法参考 tdx2db（MIT）的 `calc/`（QUANTAXIS 口径）：
除权日的理论前收盘
    pre_close = (prev_close - 现金分红 + 配股比例 × 配股价) / (1 + 送转比例 + 配股比例)
（分红/送转/配股均已归一化为“每股”口径，与 easy_tdx 的 XdxrRecord 一致。）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

__all__ = [
    "AdjustFactor",
    "adjust_bars",
    "compute_adjust_factors",
    "compute_pre_close_series",
]


class _XdxrLike(Protocol):
    """XdxrRecord 的结构子类型（避免运行时强依赖）。"""

    category: int
    year: int
    month: int
    day: int
    fenhong: float | None
    songzhuangu: float | None
    peigu: float | None
    peigujia: float | None


@dataclass
class AdjustFactor:
    date: pd.Timestamp
    hfq_factor: float
    qfq_factor: float


def _event_index(
    date_to_idx: dict[pd.Timestamp, int], sorted_dates: pd.Series, event_date: pd.Timestamp
) -> int | None:
    """将事件日期映射到交易日索引；非交易日落到其后的第一个交易日。"""
    key = event_date.normalize()
    if key in date_to_idx:
        return date_to_idx[key]
    pos = sorted_dates.searchsorted(key)
    if pos < len(sorted_dates):
        return int(pos)
    return None


def _aggregate_events(bars: pd.DataFrame, events: list[Any]) -> dict[int, dict[str, float]]:
    dates = pd.to_datetime(bars["date"]).dt.normalize().reset_index(drop=True)
    date_to_idx = {ts: i for i, ts in enumerate(dates)}
    by_idx: dict[int, dict[str, float]] = {}
    for e in events:
        if int(getattr(e, "category", 0)) != 1:
            continue
        ed = pd.Timestamp(int(e.year), int(e.month), int(e.day))
        idx = _event_index(date_to_idx, dates, ed)
        if idx is None:
            continue
        info = by_idx.setdefault(
            idx, {"fenhong": 0.0, "songzhuangu": 0.0, "peigu": 0.0, "peigujia": 0.0}
        )
        info["fenhong"] += float(e.fenhong or 0.0)
        info["songzhuangu"] += float(e.songzhuangu or 0.0)
        info["peigu"] += float(e.peigu or 0.0)
        if e.peigujia:
            info["peigujia"] = float(e.peigujia)
    return by_idx


def _theoretical_pre_close(prev_close: float, info: dict[str, float]) -> float:
    denom = 1.0 + info["peigu"] + info["songzhuangu"]
    if denom == 0:
        return prev_close
    return (prev_close - info["fenhong"] + info["peigu"] * info["peigujia"]) / denom


def compute_pre_close_series(bars: pd.DataFrame, events: list[Any] | None) -> pd.Series:
    """按除权事件计算每日的“前收盘价”（除权日已做理论调整）。"""
    df = bars.sort_values("date").reset_index(drop=True)
    by_idx = _aggregate_events(df, events or [])
    closes = df["close"].astype(float).tolist()
    out: list[float] = []
    for i in range(len(df)):
        prev = closes[i] if i == 0 else closes[i - 1]
        info = by_idx.get(i)
        out.append(_theoretical_pre_close(prev, info) if info else prev)
    return pd.Series(out, index=df.index)


def compute_adjust_factors(bars: pd.DataFrame, events: list[Any] | None) -> pd.DataFrame:
    """计算与日线对齐的复权因子。

    - ``hfq_factor``：后复权因子（累乘），最早一根为 1。
    - ``qfq_factor``：前复权因子，最新一根为 1。
    """
    df = bars.sort_values("date").reset_index(drop=True)
    by_idx = _aggregate_events(df, events or [])
    closes = df["close"].astype(float).tolist()

    factors: list[float] = []
    current = 1.0
    for i in range(len(df)):
        if i > 0:
            info = by_idx.get(i)
            if info:
                prev_close = closes[i - 1]
                theo = _theoretical_pre_close(prev_close, info)
                if prev_close and theo:
                    current *= prev_close / theo
        factors.append(current)

    last = factors[-1] if factors else 1.0
    return pd.DataFrame(
        {
            "date": df["date"].reset_index(drop=True),
            "hfq_factor": factors,
            "qfq_factor": [f / last if last else f for f in factors],
        }
    )


def adjust_bars(
    bars: pd.DataFrame,
    events: list[Any] | None,
    mode: str = "qfq",
    digits: int = 2,
) -> pd.DataFrame:
    """对不复权日线施加前/后复权，替换 OHLC 为复权价。

    Args:
        bars: 含 ``date`` 与 ``open/high/low/close`` 的日线。
        events: XdxrRecord 列表（仅 category==1 参与）。
        mode: ``"qfq"`` 或 ``"hfq"``。
        digits: 复权价保留小数位（通达信桌面端为 2 位）。
    """
    if mode not in ("qfq", "hfq"):
        raise ValueError("mode 必须是 'qfq' 或 'hfq'")
    factors = compute_adjust_factors(bars, events)
    col = f"{mode}_factor"
    df = bars.sort_values("date").reset_index(drop=True).copy()
    merged = df.merge(factors[["date", col]], on="date", how="left")
    merged[col] = merged[col].fillna(1.0)
    for price_col in ("open", "high", "low", "close"):
        if price_col in merged.columns:
            merged[price_col] = (merged[price_col] * merged[col]).round(digits)
    merged["factor"] = merged[col]
    return merged.drop(columns=[col])
