"""P2-1: require 严格模式——无匹配节点时明确失败，不静默降级（离线）。"""

from __future__ import annotations

import pytest

from easy_tdx import client as client_mod
from easy_tdx.client import TdxClient
from easy_tdx.exceptions import TdxNoCapableHostError


def _patch_no_capable(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setattr(
        client_mod, "ping_all", lambda hosts, port, timeout: [("A", 0.01), ("B", 0.02)]
    )
    monkeypatch.setattr(client_mod, "select_host", lambda *a, **k: None)
    monkeypatch.setattr(client_mod, "_probe_standard_capability", lambda *a, **k: False)
    saved: list[str] = []
    monkeypatch.setattr(client_mod, "save_best_host", lambda host: saved.append(host))
    return saved


def test_strict_require_no_match_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = _patch_no_capable(monkeypatch)
    with pytest.raises(TdxNoCapableHostError):
        TdxClient.from_best_host(hosts=["A", "B"], require=["kline"], strict=True)
    assert saved == []  # 失败时不得改写全局 best_host


def test_non_strict_require_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = _patch_no_capable(monkeypatch)
    c = TdxClient.from_best_host(hosts=["A", "B"], require=["kline"])
    try:
        assert c._host == "A"
        assert saved == ["A"]
    finally:
        c.close()
