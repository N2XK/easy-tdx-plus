"""config 读取与重试配置测试（离线）。"""

from __future__ import annotations

from pathlib import Path

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


def test_concurrent_save_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import threading

    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_FILE", tmp_path / "config.json")
    errors: list[Exception] = []

    def work(i: int) -> None:
        try:
            config.save_best_host(f"10.0.0.{i}")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert (tmp_path / "config.json").exists()


def test_mutate_serializes_concurrent_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """读-改-写必须串行化：并发的 save_* 必须看到彼此已写入的字段。"""
    import threading
    import time

    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_FILE", tmp_path / "config.json")
    config.save_best_host("9.9.9.9")

    real_load = config._load
    entered = threading.Event()
    gate = threading.Event()
    t2_snapshot: list[dict] = []

    def delayed_load() -> dict:
        name = threading.current_thread().name
        if name == "writer1":
            entered.set()
            gate.wait(2)
        snap = real_load()
        if name == "writer2":
            t2_snapshot.append(snap)
        return snap

    monkeypatch.setattr(config, "_load", delayed_load)
    t1 = threading.Thread(target=lambda: config.save_best_host("1.1.1.1"), name="writer1")
    t2 = threading.Thread(target=lambda: config.save_best_ex_host("2.2.2.2"), name="writer2")
    t1.start()
    assert entered.wait(2)
    t2.start()
    time.sleep(0.1)
    assert t2_snapshot == []  # writer1 持锁期间 writer2 不得读到快照
    gate.set()
    t1.join(3)
    t2.join(3)

    assert t2_snapshot and t2_snapshot[0].get("best_host") == "1.1.1.1"
    saved = real_load()
    assert saved["best_host"] == "1.1.1.1"
    assert saved["best_ex_host"] == "2.2.2.2"
