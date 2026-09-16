"""0x0452 特征表 / 0x051c 指数动量 / 0x051d 指数概况 测试（离线）。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.codec.price import put_price
from easy_tdx.commands.index_info import GetIndexInfoCmd
from easy_tdx.commands.index_momentum import GetIndexMomentumCmd
from easy_tdx.commands.security_feature import GetSecurityFeatureCmd
from easy_tdx.models.enums import Market


def test_feature452_request_layout() -> None:
    req = GetSecurityFeatureCmd(start=0, count=2000).build_request()
    assert req[10:12] == b"\x52\x04"  # cmd 0x0452
    payload = req[12:]
    assert len(payload) == 14
    start, count, one, zero = struct.unpack("<IIIH", payload)
    assert (start, count, one) == (0, 2000, 1)
    assert req[6:8] == struct.pack("<H", len(payload) + 2)  # 长度 = payload + 2


def test_feature452_parse() -> None:
    body = struct.pack("<H", 1) + struct.pack("<BIff", 1, 600519, 10.0, 9.5)
    items = GetSecurityFeatureCmd().parse_response(body)
    assert len(items) == 1
    assert items[0].market == 1
    assert items[0].code == "600519"
    assert items[0].p1 == pytest.approx(10.0)
    assert items[0].p2 == pytest.approx(9.5)


def test_index_momentum_request_and_parse() -> None:
    req = GetIndexMomentumCmd(Market.SH, "000001").build_request()
    assert req[10:12] == b"\x1c\x05"
    assert req[12:] == struct.pack("<H6s", 1, b"000001")
    assert req[6:8] == struct.pack("<H", len(req[12:]) + 2)

    body = struct.pack("<H", 3) + put_price(5) + put_price(-2) + put_price(4)
    values = GetIndexMomentumCmd(Market.SH, "000001").parse_response(body)
    assert values == [5, 3, 7]  # 累计


def test_index_info_request_layout() -> None:
    req = GetIndexInfoCmd(Market.SH, "000001").build_request()
    assert req[10:12] == b"\x1d\x05"
    payload = req[12:]
    assert len(payload) == 12
    assert payload[0:2] == struct.pack("<H", 1)
    assert payload[2:8] == b"000001"
    assert req[6:8] == struct.pack("<H", len(payload) + 2)
