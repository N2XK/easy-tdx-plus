"""增强 1: 公开的有界请求接口 + 请求诊断（离线）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from easy_tdx import client as client_mod
from easy_tdx.client import AsyncTdxClient, TdxClient
from easy_tdx.exceptions import TdxConnectionError


class _Cmd:
    def build_request(self) -> bytes:
        return b""

    def parse_response(self, body: bytes) -> bytes:
        return body


def _install_fake_conn(monkeypatch: pytest.MonkeyPatch, visits: list[str]) -> None:
    class _FakeConn:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.host = host
            visits.append(host)

        def connect(self) -> None:
            if self.host == "A":
                raise TdxConnectionError("refused")

        def close(self) -> None:
            pass

        def start_heartbeat(self, *args: object, **kwargs: object) -> None:
            pass

        def stop_heartbeat(self) -> None:
            pass

        def execute(self, cmd: object) -> list[str]:
            return [] if self.host == "B" else ["ok"]

    monkeypatch.setattr(client_mod, "TdxConnection", _FakeConn)


def test_request_diagnostics_match_network(monkeypatch: pytest.MonkeyPatch) -> None:
    visits: list[str] = []
    _install_fake_conn(monkeypatch, visits)
    c = TdxClient(host="SELF")
    visits.clear()  # 不计构造时的占位连接，只统计请求期实际访问

    out: Any = c.request(_Cmd(), pool=["A", "B", "C"], max_attempts=3, require_nonempty=True)

    assert out == ["ok"]
    diag = c.last_request_diagnostics
    assert diag is not None
    assert diag.hosts == ("A", "B", "C")
    assert [a.ok for a in diag.attempts] == [False, True, True]
    assert [a.empty for a in diag.attempts] == [False, True, False]
    assert diag.attempt_count == 3
    assert diag.source == "C"
    assert diag.exhausted is False
    # 诊断中的节点与尝试次数必须与实际网络访问一致
    assert visits == ["A", "B", "C"]


def test_request_pool_none_uses_only_current_host(monkeypatch: pytest.MonkeyPatch) -> None:
    visits: list[str] = []
    _install_fake_conn(monkeypatch, visits)
    c = TdxClient(host="ONLY")
    visits.clear()

    out: Any = c.request(_Cmd())
    assert out == ["ok"]
    assert visits == ["ONLY"]
    assert c.last_request_diagnostics is not None
    assert c.last_request_diagnostics.hosts == ("ONLY",)
    assert c.last_request_diagnostics.source == "ONLY"


def test_request_max_attempts_bounds_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    visits: list[str] = []
    _install_fake_conn(monkeypatch, visits)
    c = TdxClient(host="SELF")
    visits.clear()

    with pytest.raises(TdxConnectionError):
        c.request(_Cmd(), pool=["A", "B", "C"], max_attempts=2, require_nonempty=True)

    diag = c.last_request_diagnostics
    assert diag is not None
    assert diag.hosts == ("A", "B")  # 未访问 C
    assert visits == ["A", "B"]
    assert diag.exhausted is True


def test_async_request_diagnostics_match_network(monkeypatch: pytest.MonkeyPatch) -> None:
    visits: list[str] = []

    class _FakeAsyncConn:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            self.host = host
            visits.append(host)

        async def connect(self) -> None:
            if self.host == "A":
                raise TdxConnectionError("refused")

        async def close(self) -> None:
            pass

        async def execute(self, cmd: object) -> list[str]:
            return [] if self.host == "B" else ["ok"]

    monkeypatch.setattr(client_mod, "AsyncTdxConnection", _FakeAsyncConn)

    async def run() -> tuple[AsyncTdxClient, Any]:
        c = AsyncTdxClient(host="SELF", heartbeat_interval=0.0)
        visits.clear()
        out = await c.request(_Cmd(), pool=["A", "B", "C"], max_attempts=3, require_nonempty=True)
        return c, out

    c, out = asyncio.run(run())
    assert out == ["ok"]
    diag = c.last_request_diagnostics
    assert diag is not None
    assert diag.hosts == ("A", "B", "C")
    assert diag.source == "C"
    assert visits == ["A", "B", "C"]


def test_request_total_timeout_stops_new_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    visits: list[str] = []
    _install_fake_conn(monkeypatch, visits)
    c = TdxClient(host="SELF")
    visits.clear()

    ticks = iter([0.0, 0.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    monkeypatch.setattr(client_mod.time, "monotonic", lambda: next(ticks))

    with pytest.raises(TdxConnectionError):
        c.request(_Cmd(), pool=["A", "B", "C"], total_timeout=1.0, require_nonempty=True)

    # 预算耗尽后不再发起新尝试
    assert visits == ["A"]
