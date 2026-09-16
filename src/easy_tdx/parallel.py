"""并发取数：连接池 / 直连两种模式。

- ``mode="pool"``（默认）：持有 N 个 :class:`~easy_tdx.client.TdxClient` 复用（队列借用）。
- ``mode="direct"``：每个请求独立新建 TCP 连接、用完即关；高并发下更稳（参考 tdxrs 的
  ``TdxDirectClient``：60 线程近零退化，而连接池会因争用退化）。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from typing import Any, Literal, TypeVar

from .client import TdxClient
from .exceptions import TdxConnectionError

_T = TypeVar("_T")
_R = TypeVar("_R")

__all__ = ["ParallelTdx"]


class ParallelTdx:
    """N 连接并发客户端。

    Args:
        host: 服务器地址（None 时用默认最佳主机）。
        connections: 连接数（pool 模式为池大小，也是默认并发度）。
        timeout: 单请求超时。
        rate_limit: 是否为每个连接启用交易时段限流。
        client_factory: 自定义客户端工厂（测试注入用）。
        mode: ``"pool"``（默认）复用连接；``"direct"`` 每请求独立连接。
    """

    def __init__(
        self,
        host: str | None = None,
        connections: int = 4,
        timeout: float | None = None,
        rate_limit: bool = False,
        client_factory: Callable[[], TdxClient] | None = None,
        mode: Literal["pool", "direct"] = "pool",
    ) -> None:
        self.host = host
        self.connections = max(1, connections)
        self.timeout = timeout
        self.mode = mode
        self._factory = client_factory or (
            lambda: TdxClient(host, timeout=timeout, rate_limit=rate_limit)
        )
        self._pool: Queue[TdxClient] = Queue()
        self._clients: list[TdxClient] = []
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> ParallelTdx:
        with self._lock:
            if self._started:
                return self
            if self.mode == "pool":
                for _ in range(self.connections):
                    client = self._factory()
                    client.connect()
                    self._clients.append(client)
                    self._pool.put(client)
            self._started = True
        return self

    def __enter__(self) -> ParallelTdx:
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            for client in self._clients:
                try:
                    client.close()
                except Exception:
                    pass
            self._clients.clear()
            while True:
                try:
                    self._pool.get_nowait()
                except Empty:
                    break
            self._started = False

    def map(
        self,
        func: Callable[[TdxClient, _T], _R],
        items: Sequence[_T],
        workers: int | None = None,
    ) -> list[_R]:
        """并发对 ``items`` 执行 ``func(client, item)``，保持输入顺序。"""
        if not self._started:
            self.start()
        max_workers = workers or self.connections

        if self.mode == "direct":

            def run_direct(item: _T) -> _R:
                client = self._factory()
                client.connect()
                try:
                    try:
                        return func(client, item)
                    except TdxConnectionError:
                        client.close()
                        client = self._factory()
                        client.connect()
                        return func(client, item)
                finally:
                    client.close()

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                return list(executor.map(run_direct, items))

        def run(item: _T) -> _R:
            client = self._pool.get()
            try:
                try:
                    return func(client, item)
                except TdxConnectionError:
                    # 连接可能已失效：重建该连接后重试一次（读多写少场景安全）。
                    try:
                        client.close()
                    except Exception:
                        pass
                    client = self._factory()
                    client.connect()
                    return func(client, item)
            finally:
                self._pool.put(client)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(run, items))
