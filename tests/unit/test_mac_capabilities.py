"""增强 2: MAC 真实接口能力探测（离线）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from easy_tdx import config as cfg
from easy_tdx.exceptions import TdxConnectionError, TdxNoCapableHostError
from easy_tdx.mac import capabilities as mac_cap
from easy_tdx.mac import client as mac_client


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "_CONFIG_FILE", tmp_path / "config.json")


class _FakeConn:
    def __init__(self, empty: set[str] | None = None, fail_connect: bool = False) -> None:
        self.empty = empty or set()
        self.fail_connect = fail_connect
        self.closed = False

    def connect(self) -> None:
        if self.fail_connect:
            raise TdxConnectionError("refused")

    def close(self) -> None:
        self.closed = True

    def execute(self, cmd: Any) -> list[int]:
        return [] if type(cmd).__name__ in self.empty else [1]


def test_probe_distinguishes_ok_and_empty() -> None:
    conn = _FakeConn(empty={"SymbolBarCmd"})
    caps = mac_cap.probe_mac_capabilities("1.2.3.4", 7709, 1.0, connection_factory=lambda: conn)
    assert caps == {"quotes": "ok", "kline": "empty"}  # 空返回 != 成功
    assert conn.closed


def test_probe_connect_failure_is_error_not_empty() -> None:
    caps = mac_cap.probe_mac_capabilities(
        "9.9.9.9", 7709, 1.0, connection_factory=lambda: _FakeConn(fail_connect=True)
    )
    assert caps == {name: "error" for name in mac_cap.MAC_FEATURES}


def test_select_mac_host_prefers_capable() -> None:
    profiles = {
        "a": {"quotes": "ok", "kline": "empty"},
        "b": {"quotes": "ok", "kline": "ok"},
    }
    ranked = [("a", 0.01), ("b", 0.02)]
    prober = lambda h: profiles[h]  # noqa: E731
    assert mac_cap.select_mac_host(ranked, ["quotes", "kline"], prober=prober) == "b"
    assert mac_cap.select_mac_host(ranked, ["quotes"], prober=prober) == "a"
    assert mac_cap.select_mac_host(ranked, ["nope"], prober=prober) is None
    assert mac_cap.select_mac_host(ranked, None, prober=prober) is None


def test_mac_from_best_host_require_selects_capable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mac_client, "get_mac_hosts", lambda: ["a", "b"])
    monkeypatch.setattr(
        mac_client, "ping_mac_all", lambda hosts, port, timeout: [("a", 0.01), ("b", 0.02)]
    )
    monkeypatch.setattr(mac_client, "select_mac_host", lambda ranked, require, prober=None: "b")

    c = mac_client.MacClient.from_best_host(require=["quotes"])
    try:
        assert c._host == "b"
        assert cfg.get_best_mac_host() == "b"
    finally:
        c.close()


def test_mac_from_best_host_strict_require_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mac_client, "ping_mac_all", lambda hosts, port, timeout: [("a", 0.01)])
    monkeypatch.setattr(mac_client, "select_mac_host", lambda *a, **k: None)

    with pytest.raises(TdxNoCapableHostError):
        mac_client.MacClient.from_best_host(hosts=["a"], require=["quotes"], strict=True)
