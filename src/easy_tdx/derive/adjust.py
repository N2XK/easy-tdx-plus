"""派生计算：复权（QFQ/HFQ，仿射变换，对齐通达信）。

通达信桌面端/服务器端的复权是 **仿射变换**：
    adjusted = mul × raw + add
其中现金分红是“减法”，送转/配股是“乘法”。这与 tdx2db/QUANTAXIS 的
纯乘法因子不同——纯乘法在跨现金分红区间会与服务端产生偏差。

单个除权除息事件（分红 c / 送转 b / 配股 r、配股价 p，均为每股口径）把
事件前的价格映射到事件后基准：
    F(x) = x / (1 + b + r) + (r*p - c) / (1 + b + r)   （即理论除权价）
    等价于：ex_price = (x - c + r*p) / (1 + b + r)

- 后复权（HFQ）：把每日价格换算到最早基准 = C_fwd(i) 的逆
- 前复权（QFQ）：把每日价格换算到最新基准 = C_all ∘ C_fwd(i) 的逆
其中 C_fwd(i) 为事件索引 ≤ i 的仿射复合。
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

_Affine = tuple[float, float]  # (mul, add): x -> mul*x + add


class _XdxrLike(Protocol):
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
    hfq_mul: float
    hfq_add: float
    qfq_mul: float
    qfq_add: float


def _compose(outer: _Affine, inner: _Affine) -> _Affine:
    """返回 outer ∘ inner：x -> outer(inner(x))。"""
    m1, a1 = inner
    m2, a2 = outer
    return (m2 * m1, m2 * a1 + a2)


def _inverse(t: _Affine) -> _Affine:
    m, a = t
    if m == 0:
        return (1.0, 0.0)
    return (1.0 / m, -a / m)


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


def _forward_transform(info: dict[str, float]) -> _Affine:
    denom = 1.0 + info["peigu"] + info["songzhuangu"]
    if denom == 0:
        return (1.0, 0.0)
    return (1.0 / denom, (info["peigu"] * info["peigujia"] - info["fenhong"]) / denom)


def _theoretical_pre_close(prev_close: float, info: dict[str, float]) -> float:
    mul, add = _forward_transform(info)
    return mul * prev_close + add


def _cumulative_forward(df: pd.DataFrame, by_idx: dict[int, dict[str, float]]) -> list[_Affine]:
    cum: _Affine = (1.0, 0.0)
    out: list[_Affine] = []
    for i in range(len(df)):
        info = by_idx.get(i)
        if info:
            cum = _compose(_forward_transform(info), cum)
        out.append(cum)
    return out


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
    """计算与日线对齐的仿射复权系数。

    - HFQ：最早一根为原始价（mul=1, add=0）
    - QFQ：最新一根为原始价（mul=1, add=0）
    """
    df = bars.sort_values("date").reset_index(drop=True)
    by_idx = _aggregate_events(df, events or [])
    cfwd = _cumulative_forward(df, by_idx)
    c_all = cfwd[-1] if cfwd else (1.0, 0.0)

    dates = df["date"].reset_index(drop=True)
    rows: list[AdjustFactor] = []
    for i in range(len(df)):
        inv = _inverse(cfwd[i])
        hfq = inv
        qfq = _compose(c_all, inv)
        rows.append(
            AdjustFactor(
                date=dates.iloc[i],
                hfq_mul=hfq[0],
                hfq_add=hfq[1],
                qfq_mul=qfq[0],
                qfq_add=qfq[1],
            )
        )
    return pd.DataFrame([r.__dict__ for r in rows])


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
    mul_col, add_col = f"{mode}_mul", f"{mode}_add"
    df = bars.sort_values("date").reset_index(drop=True).copy()
    merged = df.merge(factors[["date", mul_col, add_col]], on="date", how="left")
    merged[mul_col] = merged[mul_col].fillna(1.0)
    merged[add_col] = merged[add_col].fillna(0.0)
    for price_col in ("open", "high", "low", "close"):
        if price_col in merged.columns:
            merged[price_col] = (merged[price_col] * merged[mul_col] + merged[add_col]).round(
                digits
            )
    return merged.drop(columns=[mul_col, add_col])
