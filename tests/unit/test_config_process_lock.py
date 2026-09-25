"""P1-4: 跨进程读-改-写必须串行化，两个进程改不同字段都要保留（离线）。"""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import pytest

from easy_tdx import config


def _worker(field: str, value: str, start: object) -> None:
    start.wait(10)  # type: ignore[attr-defined]
    if field == "best_host":
        config.save_best_host(value)
    else:
        config.save_best_ex_host(value)


def test_cross_process_mutate_preserves_both_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_FILE", tmp_path / "config.json")
    config.save_best_host("base.example")

    real_load = config._load

    def slow_load() -> dict:
        # 放大竞态窗口：无跨进程锁时两个进程会读到同一份旧快照
        time.sleep(0.3)
        return real_load()

    monkeypatch.setattr(config, "_load", slow_load)

    ctx = mp.get_context("fork")
    start = ctx.Event()
    p1 = ctx.Process(target=_worker, args=("best_host", "1.1.1.1", start))
    p2 = ctx.Process(target=_worker, args=("best_ex_host", "2.2.2.2", start))
    p1.start()
    p2.start()
    start.set()
    p1.join(15)
    p2.join(15)
    assert p1.exitcode == 0 and p2.exitcode == 0

    saved = real_load()
    assert saved["best_host"] == "1.1.1.1"  # 进程 A 的更新未被进程 B 覆盖
    assert saved["best_ex_host"] == "2.2.2.2"
