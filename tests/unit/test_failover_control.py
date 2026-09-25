"""P1-2: 关闭 failover 后 _execute_std 不得扫描备用池或改全局配置（离线）。"""

from __future__ import annotations

from typing import Any

import pytest

from easy_tdx import client as client_mod
from easy_tdx.client import TdxClient
from easy_tdx.exceptions import TdxDecodeError


class _Cmd:
    def build_request(self) -> bytes:
        return b""

    def parse_response(self, body: bytes) -> bytes:
        return body


def _guard() -> list[str]:
    raise AssertionError("禁止 failover 时不得扫描备用池")


def test_execute_std_no_failover_decode_error_does_not_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = TdxClient(host="127.0.0.1", allow_failover=False)

    def boom(cmd: object) -> Any:
        raise TdxDecodeError("bad")

    monkeypatch.setattr(c, "_execute", boom)
    monkeypatch.setattr(client_mod, "get_full_featured_hosts", _guard)
    with pytest.raises(TdxDecodeError):
        c._execute_std(_Cmd())  # type: ignore[arg-type]


def test_execute_std_no_failover_empty_does_not_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = TdxClient(host="127.0.0.1", allow_failover=False)
    monkeypatch.setattr(c, "_execute", lambda cmd: [])
    monkeypatch.setattr(client_mod, "get_full_featured_hosts", _guard)
    assert c._execute_std(_Cmd(), require_nonempty=True) == []  # type: ignore[arg-type]


def test_execute_std_failover_enabled_still_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = TdxClient(host="A", allow_failover=True)
    state = {"scans": 0, "switched": None}

    def boom(cmd: object) -> Any:
        raise TdxDecodeError("bad")

    def hosts() -> list[str]:
        state["scans"] += 1
        return ["B"]

    class _FakeConn:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def connect(self) -> None:
            pass

        def close(self) -> None:
            pass

        def start_heartbeat(self, *args: object, **kwargs: object) -> None:
            pass

        def execute(self, cmd: object) -> list[str]:
            return ["ok"]

    monkeypatch.setattr(c, "_execute", boom)
    monkeypatch.setattr(client_mod, "get_full_featured_hosts", hosts)
    monkeypatch.setattr(client_mod, "TdxConnection", _FakeConn)
    monkeypatch.setattr(c, "_switch_host", lambda host: state.__setitem__("switched", host))

    assert c._execute_std(_Cmd()) == ["ok"]  # type: ignore[arg-type]
    assert state["scans"] == 1
    assert state["switched"] == "B"
