"""config 读取与重试配置测试（离线）。"""

from __future__ import annotations

import pytest

from easy_tdx import AsyncTdxClient, TdxClient, config
from easy_tdx.exceptions import TdxConnectionError


def test_retry_delays_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASY_TDX_RETRY_DELAYS", "0.01,0.02,0.03")
    assert config.get_retry_delays() == (0.01, 0.02, 0.03)


def test_retry_delays_empty_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASY_TDX_RETRY_DELAYS", "")
    assert config.get_retry_delays() == ()


def test_client_takes_retry_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EASY_TDX_RETRY_DELAYS", "0.01")
    c = TdxClient(host="127.0.0.1")
    assert c._retry_delays == (0.01,)
    c2 = TdxClient(host="127.0.0.1", retry_delays=(0.5, 0.7))
    assert c2._retry_delays == (0.5, 0.7)


class _Cmd:
    def build_request(self) -> bytes:
        return b""

    def parse_response(self, body: bytes) -> bytes:
        return body


def test_execute_empty_retry_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1", retry_delays=())

    def boom(cmd: object) -> None:
        raise TdxConnectionError("down")

    monkeypatch.setattr(c._conn, "execute", boom)
    with pytest.raises(TdxConnectionError):
        c._execute(_Cmd())  # type: ignore[arg-type]


def test_execute_no_reconnect_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1", auto_reconnect=False, retry_delays=(0.0,))

    def boom(cmd: object) -> None:
        raise TdxConnectionError("down")

    monkeypatch.setattr(c._conn, "execute", boom)
    with pytest.raises(TdxConnectionError):
        c._execute(_Cmd())  # type: ignore[arg-type]


def test_async_client_takes_retry_delays(monkeypatch: pytest.MonkeyPatch) -> None:
    c = AsyncTdxClient(host="127.0.0.1", retry_delays=(0.1,))
    assert c._retry_delays == (0.1,)
