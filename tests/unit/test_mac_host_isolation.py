"""P1-1: MAC 选优必须与标准协议默认节点隔离（离线）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from easy_tdx import config as cfg
from easy_tdx.mac import client as mac_client


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "_CONFIG_FILE", tmp_path / "config.json")


def test_mac_best_host_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg.save_best_mac_host("121.36.248.138")
    assert cfg.get_best_mac_host() == "121.36.248.138"
    # 独立于标准协议 best_host
    assert cfg.get_best_host() != "121.36.248.138"


def test_mac_from_best_host_does_not_touch_standard_best_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg.save_best_host("180.153.18.170")
    monkeypatch.setattr(
        mac_client, "ping_mac_all", lambda hosts, port, timeout: [("121.36.248.138", 0.01)]
    )
    monkeypatch.setattr(mac_client, "get_mac_hosts", lambda: ["121.36.248.138"])

    client = mac_client.MacClient.from_best_host()
    try:
        # MAC 选中的节点写入独立键
        assert cfg.get_best_mac_host() == "121.36.248.138"
        # 标准协议默认节点保持不变
        assert cfg.get_best_host() == "180.153.18.170"
    finally:
        client.close()


def test_async_mac_from_best_host_does_not_touch_standard_best_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg.save_best_host("180.153.18.170")
    monkeypatch.setattr(
        mac_client, "ping_mac_all", lambda hosts, port, timeout: [("121.36.248.138", 0.01)]
    )
    monkeypatch.setattr(mac_client, "get_mac_hosts", lambda: ["121.36.248.138"])

    client = mac_client.AsyncMacClient.from_best_host()
    assert cfg.get_best_mac_host() == "121.36.248.138"
    assert cfg.get_best_host() == "180.153.18.170"
    assert client._host == "121.36.248.138"


def test_mac_client_default_host_uses_mac_best(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg.save_best_host("180.153.18.170")
    cfg.save_best_mac_host("121.36.248.138")
    client = mac_client.MacClient()
    try:
        assert client._host == "121.36.248.138"
    finally:
        client.close()
