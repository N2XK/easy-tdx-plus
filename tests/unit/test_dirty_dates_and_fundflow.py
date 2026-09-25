"""脏日期容错 + 资金流回退走 _execute_std（离线）。"""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from easy_tdx import client as client_mod
from easy_tdx._df import _merge_bar_datetime
from easy_tdx.client import TdxClient
from easy_tdx.codec.configdata import parse_index_names


def test_merge_bar_datetime_drops_invalid_dates() -> None:
    df = pd.DataFrame(
        [
            {"year": 2026, "month": 9, "day": 24, "hour": 15, "minute": 0},
            {"year": 0, "month": 0, "day": 0, "hour": 0, "minute": 0},  # 脏日期
            {"year": 2026, "month": 9, "day": 23, "hour": 15, "minute": 0},
        ]
    )
    out = _merge_bar_datetime(df, daily_plus=True)
    assert list(out.columns)[0] == "date"
    assert len(out) == 2  # 脏行被丢弃，未抛异常
    assert out["date"].notna().all()


def test_parse_index_names_variable_field_count() -> None:
    raw = ("1|000001||上证指数\n62|000985|||所有A股股票的综合指数\n").encode("gbk")
    names = {r.code: r.name for r in parse_index_names(raw)}
    assert names["000001"] == "上证指数"
    assert names["000985"] == "所有A股股票的综合指数"


class _Bar:
    year = 2026
    month = 9
    day = 24


def test_fund_flow_fallback_uses_execute_std(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1")
    # 直连资金流命令返回空 → 走兼容回退
    monkeypatch.setattr(c, "_execute", lambda cmd: [])
    calls = {"bars": 0, "txn": 0}

    def fake_std(cmd: Any, *, require_nonempty: bool = False) -> list[Any]:
        name = type(cmd).__name__
        if name == "GetSecurityBarsCmd":
            calls["bars"] += 1
            return [_Bar()]
        calls["txn"] += 1
        return []

    monkeypatch.setattr(c, "_execute_std", fake_std)
    df = c.get_history_fund_flow(client_mod.Market.SH, "600519", 0, 1)

    assert calls["bars"] == 1  # 日线回退使用了 _execute_std
    assert not df.empty and "date" in df.columns
