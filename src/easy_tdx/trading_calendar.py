"""交易日历工具。

A 股的交易日并非"工作日"（存在法定节假日、调休），因此本模块**不内置节假日表**，
而是接受一组真实的交易日（通常来自指数日线，如 `上证指数 (SH, 000001)`），
在其上提供判断与前后跳转：

    from easy_tdx import TdxClient
    cal = TdxClient.from_best_host().get_trading_calendar(20240101)
    cal.is_trading_day(20240102)          # True
    cal.prev_trading_day(20240108)        # 2024-01-05
    cal.next_trading_day(20240105)        # 2024-01-08

纯逻辑部分（`TradingCalendar`）不依赖网络，可离线单测。
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

__all__ = [
    "TradingCalendar",
    "is_trading_day",
    "prev_trading_day",
    "next_trading_day",
]


def _to_date(value: Any) -> date:
    """把 date/datetime/YYYYMMDD(int)/字符串 归一为 `datetime.date`。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int):
        return datetime.strptime(str(value), "%Y%m%d").date()
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    raise TypeError(f"无法解析为日期: {value!r}")


@dataclass
class TradingCalendar:
    """基于真实交易日集合的日历。

    Args:
        days: 交易日序列（可含重复/乱序，构造时自动排序去重）。
    """

    days: list[date] = field(default_factory=list)
    _set: frozenset[date] = field(default_factory=frozenset, init=False, repr=False)

    def __post_init__(self) -> None:
        self.days = sorted({_to_date(d) for d in self.days})
        self._set = frozenset(self.days)

    # -- 构造 ------------------------------------------------------------- #

    @classmethod
    def from_bars(cls, bars: pd.DataFrame, date_col: str = "date") -> TradingCalendar:
        """从含日期列的行情 DataFrame 构造。"""
        if date_col not in bars.columns:
            raise ValueError(f"缺少日期列: {date_col!r}")
        return cls([ts.date() for ts in pd.to_datetime(bars[date_col])])

    @classmethod
    def from_weekdays(
        cls, start: Any, end: Any, holidays: Iterable[Any] | None = None
    ) -> TradingCalendar:
        """工作日近似日历（可选排除 holidays）。**不含法定节假日表**，仅作兜底。"""
        start_d, end_d = _to_date(start), _to_date(end)
        skip = {_to_date(h) for h in holidays or []}
        days: list[date] = []
        cur = start_d
        while cur <= end_d:
            if cur.weekday() < 5 and cur not in skip:
                days.append(cur)
            cur += timedelta(days=1)
        return cls(days)

    # -- 查询 ------------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self.days)

    def __contains__(self, value: object) -> bool:
        try:
            return _to_date(value) in self._set
        except TypeError:
            return False

    @property
    def first(self) -> date | None:
        return self.days[0] if self.days else None

    @property
    def last(self) -> date | None:
        return self.days[-1] if self.days else None

    def is_trading_day(self, value: Any) -> bool:
        return _to_date(value) in self._set

    def prev_trading_day(self, value: Any, n: int = 1) -> date | None:
        """严格早于 value 的第 n 个交易日（value 为交易日本身时从其前一个算起）。"""
        if n < 1:
            raise ValueError("n 必须 >= 1")
        i = bisect_left(self.days, _to_date(value)) - n
        return self.days[i] if 0 <= i < len(self.days) else None

    def next_trading_day(self, value: Any, n: int = 1) -> date | None:
        """严格晚于 value 的第 n 个交易日。"""
        if n < 1:
            raise ValueError("n 必须 >= 1")
        i = bisect_right(self.days, _to_date(value)) + n - 1
        return self.days[i] if 0 <= i < len(self.days) else None

    def trading_days_between(self, start: Any, end: Any, inclusive: bool = True) -> list[date]:
        """闭区间 [start, end] 内的交易日（inclusive=False 时为开区间，不含两端）。"""
        s, e = _to_date(start), _to_date(end)
        lo = bisect_right(self.days, s) if not inclusive else bisect_left(self.days, s)
        hi = bisect_left(self.days, e) if not inclusive else bisect_right(self.days, e)
        return self.days[lo:hi]

    def count_trading_days(self, start: Any, end: Any, inclusive: bool = True) -> int:
        return len(self.trading_days_between(start, end, inclusive=inclusive))

    def recent(self, n: int = 5) -> list[date]:
        """最近 n 个交易日（升序）。"""
        if n < 1:
            raise ValueError("n 必须 >= 1")
        return self.days[-n:]

    def as_ints(self) -> list[int]:
        """返回 YYYYMMDD 整数列表，可直接传给按日期的接口。"""
        return [d.year * 10000 + d.month * 100 + d.day for d in self.days]


# -- 模块级便捷函数（基于一次性构造的日历） --------------------------------- #


def is_trading_day(value: Any, calendar: TradingCalendar) -> bool:
    return calendar.is_trading_day(value)


def prev_trading_day(value: Any, calendar: TradingCalendar, n: int = 1) -> date | None:
    return calendar.prev_trading_day(value, n)


def next_trading_day(value: Any, calendar: TradingCalendar, n: int = 1) -> date | None:
    return calendar.next_trading_day(value, n)
