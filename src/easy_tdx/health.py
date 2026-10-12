"""主机健康评分和熔断工具。

网络主站质量会随运营商、时段和命令变化。该模块不改变现有默认选路，只提供
可注入的、线程安全的运行时评分器，供连接池或采集任务使用。
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class EndpointHealth:
    endpoint: str
    successes: int = 0
    failures: int = 0
    ewma_latency_ms: float | None = None
    opened_at: float | None = None
    last_error: str | None = None

    @property
    def failure_rate(self) -> float:
        total = self.successes + self.failures
        return self.failures / total if total else 0.0

    @property
    def circuit_open(self) -> bool:
        return self.opened_at is not None and self.opened_at > time.monotonic()


class HostHealthRegistry:
    """带冷却时间的轻量熔断和主机评分器。"""

    def __init__(self, *, failure_threshold: int = 3, cooldown: float = 30.0) -> None:
        if failure_threshold < 1 or cooldown <= 0:
            raise ValueError("failure_threshold must be >= 1 and cooldown > 0")
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self._lock = threading.Lock()
        self._states: dict[str, EndpointHealth] = {}

    def record_success(self, endpoint: str, latency_ms: float | None = None) -> None:
        with self._lock:
            old = self._states.get(endpoint, EndpointHealth(endpoint))
            latency = old.ewma_latency_ms
            if latency_ms is not None:
                latency = latency_ms if latency is None else latency * 0.8 + latency_ms * 0.2
            self._states[endpoint] = EndpointHealth(
                endpoint,
                old.successes + 1,
                old.failures,
                latency,
                None,
                None,
            )

    def record_failure(self, endpoint: str, error: BaseException | str) -> None:
        with self._lock:
            old = self._states.get(endpoint, EndpointHealth(endpoint))
            failures = old.failures + 1
            opened = (
                time.monotonic() + self.cooldown
                if failures >= self.failure_threshold
                else old.opened_at
            )
            self._states[endpoint] = EndpointHealth(
                endpoint,
                old.successes,
                failures,
                old.ewma_latency_ms,
                opened,
                str(error),
            )

    def is_available(self, endpoint: str) -> bool:
        state = self.snapshot().get(endpoint)
        return state is None or not state.circuit_open

    def rank(self, endpoints: list[str]) -> list[str]:
        states = self.snapshot()
        now = time.monotonic()
        return sorted(
            endpoints,
            key=lambda endpoint: (
                states.get(endpoint, EndpointHealth(endpoint)).circuit_open
                and (states[endpoint].opened_at or now) > now,
                states.get(endpoint, EndpointHealth(endpoint)).failure_rate,
                states.get(endpoint, EndpointHealth(endpoint)).ewma_latency_ms or float("inf"),
            ),
        )

    def snapshot(self) -> dict[str, EndpointHealth]:
        with self._lock:
            return dict(self._states)


__all__ = ["EndpointHealth", "HostHealthRegistry"]
