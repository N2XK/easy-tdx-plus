"""分时副图（0x051b）测试：请求布局、响应解析、selector 解析（离线）。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.commands.minute_aux import GetMinuteAuxCmd, resolve_selector
from easy_tdx.models.enums import Market


def test_aux_request_layout() -> None:
    cmd = GetMinuteAuxCmd(Market.SH, "600519", 0x0B)
    req = cmd.build_request()
    assert req[10:12] == b"\x1b\x05"  # cmd = 0x051b
    payload = req[12:]
    assert len(payload) == 30
    assert payload[0:2] == struct.pack("<H", 1)  # market SH
    assert payload[2:8] == b"600519"
    assert payload[27] == 0x0B  # selector 位于偏移 27


def test_parse_buy_sell() -> None:
    body = struct.pack("<H", 2) + bytes([15, 46, 20, 30])
    points = GetMinuteAuxCmd(Market.SH, "600519", 0x00).parse_response(body)
    assert [(p.buy, p.sell) for p in points] == [(15, 46), (20, 30)]
    assert [p.index for p in points] == [0, 1]


def test_parse_volume_compare() -> None:
    body = struct.pack("<H", 2) + struct.pack("<ffff", 689.0, 745.0, 1.5, 2.5)
    points = GetMinuteAuxCmd(Market.SH, "600519", 0x0B).parse_response(body)
    assert points[0].series_a == pytest.approx(689.0)
    assert points[0].series_b == pytest.approx(745.0)
    assert points[1].series_a == pytest.approx(1.5)


def test_resolve_selector() -> None:
    assert resolve_selector("buy_sell_strength") == 0x00
    assert resolve_selector("volume_comparison") == 0x0B
    assert resolve_selector(3) == 3
    with pytest.raises(ValueError):
        resolve_selector("nope")


def test_add_minute_aux_time() -> None:
    import pandas as pd

    from easy_tdx._df import _add_minute_aux_time

    df = pd.DataFrame({"index": [0, 119, 120, 239], "buy": [0, 0, 0, 0]})
    out = _add_minute_aux_time(df)
    assert [str(t) for t in out["time"]] == ["09:31:00", "11:30:00", "13:01:00", "15:00:00"]
