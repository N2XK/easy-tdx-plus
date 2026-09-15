"""派生计算：每日基础指标（前收盘 / 涨跌幅 / 换手率 / 市值）。

口径参考 tdx2db（MIT）的 ``calc/basic.go``（QUANTAXIS）。
假设 ``vol`` 与 ``float_shares`` 单位一致（股）；换手率为百分比。
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .adjust import compute_pre_close_series

__all__ = ["compute_basic_daily"]


def compute_basic_daily(
    bars: pd.DataFrame,
    events: list[Any] | None = None,
    float_shares: float = 0.0,
    total_shares: float = 0.0,
) -> pd.DataFrame:
    """计算每日基础指标。

    Args:
        bars: 不复权日线，含 ``date/open/high/low/close/vol``。
        events: XdxrRecord 列表（用于除权日的前收盘调整）。
        float_shares: 流通股本（股）。
        total_shares: 总股本（股）。

    Returns:
        含 ``pre_close/change_pct/amplitude`` 以及（股本已知时）
        ``turnover_pct/float_mv/total_mv`` 的 DataFrame。
    """
    df = bars.sort_values("date").reset_index(drop=True).copy()
    pre_close = compute_pre_close_series(df, events)
    df["pre_close"] = pre_close.round(3)
    df["change_pct"] = ((df["close"] - pre_close) / pre_close * 100).round(2)
    df["amplitude"] = ((df["high"] - df["low"]) / pre_close * 100).round(2)

    if float_shares > 0:
        df["turnover_pct"] = (df["vol"] / float_shares * 100).round(4)
        df["float_mv"] = (df["close"] * float_shares).round(2)
    if total_shares > 0:
        df["total_mv"] = (df["close"] * total_shares).round(2)
    return df
