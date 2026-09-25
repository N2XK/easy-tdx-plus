"""P1-3: 重试循环内建连失败必须继续退避，而不是立即退出（离线）。"""

from __future__ import annotations

import asyncio

import pytest

from easy_tdx import client as client_mod
from easy_tdx.client import AsyncTdxClient, TdxClient
from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.mac import client as mac_client


class _Cmd:
    def build_request(self) -> bytes:
        return b""

    def parse_response(self, body: bytes) -> bytes:
        return body


def _boom(cmd: object) -> None:
    raise TdxConnectionError("down")


class _FakeSyncConn:
    connects = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def connect(self) -> None:
        type(self).connects += 1
        if type(self).connects == 1:
            raise TdxConnectionError("connect refused")

    def close(self) -> None:
        pass

    def start_heartbeat(self, *args: object, **kwargs: object) -> None:
        pass

    def stop_heartbeat(self) -> None:
        pass

    def execute(self, cmd: object) -> str:
        return "ok"


def test_sync_retry_continues_after_first_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSyncConn.connects = 0
    c = TdxClient(host="127.0.0.1", retry_delays=(0.0, 0.0))
    monkeypatch.setattr(c._conn, "execute", _boom)
    monkeypatch.setattr(client_mod, "TdxConnection", _FakeSyncConn)

    assert c._execute(_Cmd()) == "ok"  # type: ignore[arg-type]
    assert _FakeSyncConn.connects == 2  # 第一次建连失败后仍继续第二次


class _FakeAsyncConn:
    connects = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def connect(self) -> None:
        type(self).connects += 1
        if type(self).connects == 1:
            raise TdxConnectionError("connect refused")

    async def close(self) -> None:
        pass

    async def execute(self, cmd: object) -> str:
        return "ok"


def test_async_retry_continues_after_first_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAsyncConn.connects = 0

    async def run() -> str:
        c = AsyncTdxClient(host="127.0.0.1", retry_delays=(0.0, 0.0))

        async def boom(cmd: object) -> None:
            raise TdxConnectionError("down")

        monkeypatch.setattr(c._conn, "execute", boom)
        monkeypatch.setattr(client_mod, "AsyncTdxConnection", _FakeAsyncConn)
        return await c._execute(_Cmd())  # type: ignore[arg-type]

    assert asyncio.run(run()) == "ok"
    assert _FakeAsyncConn.connects == 2


class _FakeAsyncMacConn:
    connects = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def connect(self) -> None:
        type(self).connects += 1
        if type(self).connects == 1:
            raise TdxConnectionError("connect refused")

    async def close(self) -> None:
        pass

    async def execute(self, cmd: object) -> str:
        return "ok"


def test_async_mac_retry_continues_after_first_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mac_client, "_RETRY_DELAYS", (0.0, 0.0))
    _FakeAsyncMacConn.connects = 0

    async def run() -> str:
        c = mac_client.AsyncMacClient(host="127.0.0.1", heartbeat_interval=0.0)

        async def boom(cmd: object) -> None:
            raise TdxConnectionError("down")

        monkeypatch.setattr(c._conn, "execute", boom)
        monkeypatch.setattr(mac_client, "AsyncTdxConnection", _FakeAsyncMacConn)
        return await c._execute(_Cmd())  # type: ignore[arg-type]

    assert asyncio.run(run()) == "ok"
    assert _FakeAsyncMacConn.connects == 2


def test_mac_retry_continues_after_first_connect_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mac_client, "_RETRY_DELAYS", (0.0, 0.0))
    _FakeSyncConn.connects = 0
    c = mac_client.MacClient(host="127.0.0.1")
    monkeypatch.setattr(c._conn, "execute", _boom)
    monkeypatch.setattr(mac_client, "TdxConnection", _FakeSyncConn)

    try:
        assert c._execute(_Cmd()) == "ok"  # type: ignore[arg-type]
        assert _FakeSyncConn.connects == 2
    finally:
        c.close()
