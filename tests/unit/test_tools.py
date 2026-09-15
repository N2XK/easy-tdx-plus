"""限流 / 校验 / 基金 / tuple 输出 测试（离线）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import pytest

from easy_tdx import classify_fund, is_fund, to_tuples
from easy_tdx.exceptions import TdxValidationError
from easy_tdx.ratelimit import RateLimiter, detect_phase
from easy_tdx.validation import check_bars, validate_bars

# --------------------------------------------------------------------------- #
# 限流
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "now,expected",
    [
        (datetime(2026, 9, 15, 10, 0), "trading"),  # 周二盘中
        (datetime(2026, 9, 15, 12, 0), "prepost"),  # 午间
        (datetime(2026, 9, 15, 16, 0), "closed"),  # 收盘后
        (datetime(2026, 9, 19, 10, 0), "closed"),  # 周六
    ],
)
def test_detect_phase(now: datetime, expected: str) -> None:
    assert detect_phase(now) == expected


class _FakeClock:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.t

    def sleep(self, d: float) -> None:
        self.sleeps.append(d)
        self.t += d


def test_rate_limiter_spacing() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(
        rates={"closed": 10.0}, phase="closed", clock=clock.time, sleep=clock.sleep
    )
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    # 10 req/s -> 间隔 0.1s；首次无休眠，之后每次休眠 0.1
    assert clock.sleeps == [pytest.approx(0.1), pytest.approx(0.1)]


def test_rate_limiter_zero_means_unlimited() -> None:
    clock = _FakeClock()
    limiter = RateLimiter(rates={"closed": 0.0}, clock=clock.time, sleep=clock.sleep)
    for _ in range(5):
        limiter.acquire()
    assert clock.sleeps == []


def test_rate_limiter_set_phase() -> None:
    limiter = RateLimiter()
    limiter.set_phase("trading")
    assert limiter.phase == "trading"
    with pytest.raises(ValueError):
        limiter.set_phase("bad")


# --------------------------------------------------------------------------- #
# 校验
# --------------------------------------------------------------------------- #


def _good_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [10.0, 11.0],
            "high": [12.0, 12.5],
            "low": [9.0, 10.5],
            "close": [11.0, 12.0],
            "vol": [100.0, 200.0],
        }
    )


def test_check_bars_ok() -> None:
    assert check_bars(_good_bars()) == []
    validate_bars(_good_bars())  # 不抛异常


def test_check_bars_detects_issues() -> None:
    df = _good_bars()
    df.loc[0, "high"] = 1.0  # high < open/close/low
    df.loc[1, "vol"] = -1.0
    issues = check_bars(df)
    assert any("high" in i for i in issues)
    assert any("负成交量" in i for i in issues)
    with pytest.raises(TdxValidationError):
        validate_bars(df)


def test_check_bars_empty() -> None:
    assert check_bars(pd.DataFrame()) == []


# --------------------------------------------------------------------------- #
# 基金分类
# --------------------------------------------------------------------------- #


def test_classify_fund() -> None:
    assert classify_fund("510300") == "etf"
    assert classify_fund("sh510300") == "etf"
    assert classify_fund("159915") == "etf"
    assert classify_fund("160105") == "lof"
    assert classify_fund("508000") == "reits"
    assert classify_fund("519003") == "otc"
    assert classify_fund("600519") is None
    assert classify_fund("000001") is None
    assert is_fund("510300") and not is_fund("600519")


# --------------------------------------------------------------------------- #
# tuple 输出
# --------------------------------------------------------------------------- #


@dataclass
class _Rec:
    a: int
    b: str
    _raw: bytes = b"hidden"


def test_to_tuples() -> None:
    assert to_tuples([_Rec(1, "x"), _Rec(2, "y")]) == [(1, "x"), (2, "y")]
    assert to_tuples(_Rec(3, "z")) == [(3, "z")]
    assert to_tuples([]) == []
