"""交易日历工具测试（离线，纯逻辑）。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from easy_tdx import TradingCalendar

# 一段真实交易日（2024-01-02 ~ 2024-01-12，含周末间隔）
_DAYS = [
    date(2024, 1, 2),
    date(2024, 1, 3),
    date(2024, 1, 4),
    date(2024, 1, 5),
    date(2024, 1, 8),
    date(2024, 1, 9),
    date(2024, 1, 10),
    date(2024, 1, 11),
    date(2024, 1, 12),
]


def _cal() -> TradingCalendar:
    return TradingCalendar(_DAYS)


def test_normalize_and_sort() -> None:
    cal = TradingCalendar([20240103, "2024-01-02", date(2024, 1, 3)])
    assert cal.days == [date(2024, 1, 2), date(2024, 1, 3)]
    assert cal.first == date(2024, 1, 2) and cal.last == date(2024, 1, 3)


def test_is_trading_day() -> None:
    cal = _cal()
    assert cal.is_trading_day(20240102)
    assert cal.is_trading_day(date(2024, 1, 5))
    assert not cal.is_trading_day(20240106)  # 周六
    assert date(2024, 1, 2) in cal
    assert "2024-01-06" not in cal


def test_prev_next_trading_day() -> None:
    cal = _cal()
    assert cal.prev_trading_day(20240108) == date(2024, 1, 5)  # 跨越周末
    assert cal.prev_trading_day(20240105) == date(2024, 1, 4)
    assert cal.next_trading_day(20240105) == date(2024, 1, 8)
    assert cal.next_trading_day(20240106) == date(2024, 1, 8)  # 非交易日
    assert cal.prev_trading_day(20240102) is None
    assert cal.next_trading_day(20240112) is None


def test_prev_next_multi_step() -> None:
    cal = _cal()
    assert cal.prev_trading_day(20240112, 3) == date(2024, 1, 9)
    assert cal.next_trading_day(20240102, 2) == date(2024, 1, 4)


def test_trading_days_between_and_count() -> None:
    cal = _cal()
    assert cal.trading_days_between(20240102, 20240105) == _DAYS[:4]
    assert cal.count_trading_days(20240102, 20240112) == 9
    assert cal.count_trading_days(20240104, 20240109, inclusive=False) == 2


def test_recent_and_as_ints() -> None:
    cal = _cal()
    assert cal.recent(2) == [date(2024, 1, 11), date(2024, 1, 12)]
    assert cal.as_ints()[-3:] == [20240110, 20240111, 20240112]


def test_from_bars() -> None:
    bars = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])})
    cal = TradingCalendar.from_bars(bars)
    assert cal.as_ints() == [20240102, 20240103, 20240104]


def test_from_weekdays_excludes_holidays() -> None:
    cal = TradingCalendar.from_weekdays(20240101, 20240107, holidays=[20240103])
    assert cal.as_ints() == [20240101, 20240102, 20240104, 20240105]  # 排除元旦与 1/3


def test_invalid_inputs() -> None:
    cal = _cal()
    with pytest.raises(ValueError):
        cal.recent(0)
    with pytest.raises(ValueError):
        cal.prev_trading_day(20240105, 0)
    with pytest.raises(TypeError):
        cal.is_trading_day(object())
    with pytest.raises(ValueError):
        TradingCalendar.from_bars(pd.DataFrame({"close": [1.0]}))


def test_client_calendar_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    from easy_tdx import KlineCategory, Market, TdxClient

    c = TdxClient(host="127.0.0.1")
    calls: list[tuple[int, int]] = []

    def fake(
        market: Market,
        code: str,
        start: int,
        end: int,
        category: KlineCategory = KlineCategory.DAY,
        count: int = 800,
    ) -> pd.DataFrame:
        calls.append((start, end))
        return pd.DataFrame({"date": pd.to_datetime(["2024-01-02", "2024-01-03"])})

    monkeypatch.setattr(c, "get_bars_range", fake)
    cal1 = c.get_trading_calendar(20240101, 20240131)
    cal2 = c.get_trading_calendar(20240101, 20240131)
    assert len(calls) == 1  # 第二次命中缓存，不再请求
    assert cal1.days == cal2.days
    assert c.get_trading_days(20240101, 20240131) == cal1.days
