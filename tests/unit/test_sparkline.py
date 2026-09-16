"""小走势图（0x0fd1）测试：请求布局与响应解析（离线）。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.commands.sparkline import GetSparklineCmd
from easy_tdx.models.enums import Market


def test_sparkline_request_layout() -> None:
    cmd = GetSparklineCmd(Market.SZ, "000001", selector=1, window=20)
    req = cmd.build_request()
    assert req[10:12] == b"\xd1\x0f"  # cmd = 0x0fd1
    payload = req[12:]
    assert len(payload) == 39
    assert payload[0:2] == struct.pack("<H", 0)
    assert payload[2:8] == b"000001"
    assert payload[24:26] == struct.pack("<H", 1)  # selector
    assert payload[26:28] == struct.pack("<H", 20)  # window


def _body(selector: int, base: float, prices: list[float]) -> bytes:
    body = struct.pack("<H22s", 1, b"600519")
    body += struct.pack("<H", selector)
    body += struct.pack("<H", 0)
    body += b"\x00" * 6
    body += struct.pack("<H", 60)  # max_count
    body += struct.pack("<f", base)
    body += struct.pack("<H", len(prices))
    body += struct.pack("<" + "f" * len(prices), *prices)
    return body


def test_sparkline_parse_response() -> None:
    series = GetSparklineCmd(Market.SH, "600519", 1, 20).parse_response(
        _body(1, 11.82, [11.8, 11.9, 12.0])
    )
    assert series.market == 1
    assert series.code == "600519"
    assert series.selector == 1
    assert series.max_count == 60
    assert series.base_price == pytest.approx(11.82)
    assert series.prices == pytest.approx([11.8, 11.9, 12.0])


def test_sparkline_empty() -> None:
    series = GetSparklineCmd(Market.SH, "600519").parse_response(_body(1, 1272.75, []))
    assert series.prices == []
    assert series.base_price == pytest.approx(1272.75)
