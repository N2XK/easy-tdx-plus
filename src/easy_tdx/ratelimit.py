"""交易时段自适应限流。

参考 tdxrs 的思路：在交易活跃时段降低请求频率，非交易时段放宽，避免对
公共服务器造成压力、降低被限流/封禁的风险。

用法::

    limiter = RateLimiter()
    limiter.auto_detect_phase()
    limiter.acquire()   # 阻塞至允许下一次请求
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

__all__ = ["RateLimiter", "detect_phase", "DEFAULT_RATES"]

_SHANGHAI = ZoneInfo("Asia/Shanghai")

# 各时段默认速率（每秒请求数）
DEFAULT_RATES: dict[str, float] = {
    "trading": 15.0,  # 盘中 9:30-11:30 / 13:00-15:00
    "prepost": 30.0,  # 盘前盘后 9:00-9:30 / 11:30-13:00 / 15:00-15:30
    "closed": 60.0,  # 休市
}


def detect_phase(now: datetime | None = None) -> str:
    """返回当前交易时段：``trading`` / ``prepost`` / ``closed``。

    仅按工作日 + 时间判断，不含节假日日历。
    """
    now = now or datetime.now(_SHANGHAI)
    if now.weekday() >= 5:
        return "closed"
    t = now.time()
    if dtime(9, 30) <= t < dtime(11, 30) or dtime(13, 0) <= t < dtime(15, 0):
        return "trading"
    if dtime(9, 0) <= t < dtime(15, 30):
        return "prepost"
    return "closed"


class RateLimiter:
    """串行的匀速限流器（线程安全）。

    Args:
        rates: 时段 → 每秒请求数；``<=0`` 表示不限流。
        phase: 初始时段，默认 ``closed``。
        clock: 单调时钟（便于测试注入）。
        sleep: 休眠函数（便于测试注入）。
    """

    def __init__(
        self,
        rates: dict[str, float] | None = None,
        phase: str = "closed",
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rates = dict(rates or DEFAULT_RATES)
        self.phase = phase
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._next_at = 0.0

    def set_phase(self, phase: str) -> None:
        if phase not in ("trading", "prepost", "closed"):
            raise ValueError("phase 必须是 trading / prepost / closed")
        self.phase = phase

    def auto_detect_phase(self, now: datetime | None = None) -> str:
        self.phase = detect_phase(now)
        return self.phase

    def acquire(self) -> None:
        """阻塞至允许下一次请求。"""
        rate = self.rates.get(self.phase, 0.0)
        if rate <= 0:
            return
        interval = 1.0 / rate
        with self._lock:
            now = self._clock()
            if now < self._next_at:
                self._sleep(self._next_at - now)
                now = self._clock()
            self._next_at = max(now, self._next_at) + interval
