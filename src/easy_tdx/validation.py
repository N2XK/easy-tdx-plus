"""响应语义校验（纯函数）。

用于在写入下游（数据库/回测）前发现明显的畸形数据：非有限值、
OHLC 关系非法、负成交量、日期越界等。参考 xmtdx 的 validation 思路。
"""

from __future__ import annotations

import math

import pandas as pd

from .exceptions import TdxValidationError

__all__ = ["check_bars", "validate_bars"]

_OHLC = ("open", "high", "low", "close")


def check_bars(df: pd.DataFrame, context: str = "bars") -> list[str]:
    """检查 K 线 DataFrame，返回问题描述列表（空表示通过）。"""
    issues: list[str] = []
    if df is None or df.empty:
        return issues

    for col in _OHLC:
        if col in df.columns:
            series = df[col]
            if series.map(lambda x: not math.isfinite(x)).any():
                issues.append(f"{context}: {col} 含非有限值")

    if set(_OHLC) <= set(df.columns):
        bad_high = df[df["high"] + 1e-6 < df[["open", "close", "low"]].max(axis=1)]
        if len(bad_high):
            issues.append(f"{context}: {len(bad_high)} 行 high 关系非法")
        bad_low = df[df["low"] - 1e-6 > df[["open", "close", "high"]].min(axis=1)]
        if len(bad_low):
            issues.append(f"{context}: {len(bad_low)} 行 low 关系非法")

    if "vol" in df.columns and (df["vol"] < 0).any():
        issues.append(f"{context}: 存在负成交量")
    if "amount" in df.columns and (df["amount"] < 0).any():
        issues.append(f"{context}: 存在负成交额")

    return issues


def validate_bars(df: pd.DataFrame, context: str = "bars") -> pd.DataFrame:
    """检查 K 线，发现问题时抛 :class:`TdxValidationError`；否则原样返回。"""
    issues = check_bars(df, context)
    if issues:
        raise TdxValidationError("; ".join(issues))
    return df
