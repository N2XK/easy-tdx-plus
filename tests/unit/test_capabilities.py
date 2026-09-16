"""服务器能力探测与选路测试（离线）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from easy_tdx import capabilities as cap
from easy_tdx import config as cfg


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cfg, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cfg, "_CONFIG_FILE", tmp_path / "config.json")
    cap._CACHE.clear()


class _FakeConn:
    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.closed = False

    def connect(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def execute(self, cmd: Any) -> list[int]:
        name = type(cmd).__name__
        return [] if name in self.missing else [1]


def test_probe_capabilities_injected() -> None:
    missing = {"GetFinanceInfoCmd"}
    conn = _FakeConn(missing)
    caps = cap.probe_capabilities("1.2.3.4", 7709, 1.0, connection_factory=lambda: conn)
    assert set(caps) == set(cap.FEATURES)
    assert caps["quotes"] is True and caps["kline"] is True
    assert caps["finance"] is False
    assert conn.closed

    # 已持久化到 config
    saved = cfg.get_capability_cache()
    assert saved["1.2.3.4:7709"]["caps"]["finance"] is False


def test_probe_capabilities_cache_hit() -> None:
    cap.probe_capabilities("1.2.3.4", 7709, 1.0, connection_factory=lambda: _FakeConn())

    def boom() -> Any:
        raise AssertionError("命中缓存时不应再建连接")

    caps = cap.probe_capabilities("1.2.3.4", 7709, 1.0, connection_factory=boom)
    assert caps["quotes"] is True


def test_probe_capabilities_connection_error() -> None:
    def boom() -> Any:
        raise OSError("refused")

    caps = cap.probe_capabilities("9.9.9.9", 7709, 0.1, connection_factory=boom)
    assert caps == {name: False for name in cap.FEATURES}


def test_select_host_prefers_capable() -> None:
    profiles = {
        "a": {"kline": True, "transaction": False},
        "b": {"kline": True, "transaction": True},
    }
    ranked = [("a", 0.01), ("b", 0.02)]
    prober = lambda h, p, t: profiles[h]  # noqa: E731
    assert cap.select_host(ranked, ["kline", "transaction"], 7709, 1.0, prober=prober) == "b"
    assert cap.select_host(ranked, ["kline"], 7709, 1.0, prober=prober) == "a"
    assert cap.select_host(ranked, ["nope"], 7709, 1.0, prober=prober) is None
    assert cap.select_host(ranked, None, 7709, 1.0) is None
