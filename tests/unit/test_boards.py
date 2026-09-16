"""排行榜 0x053f / 成交分布 0x051a 测试（离线）。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.commands.top_board import CATEGORIES, GetTopBoardCmd
from easy_tdx.commands.volume_profile import GetVolumeProfileCmd
from easy_tdx.models.enums import Market


def test_top_board_request_layout() -> None:
    req = GetTopBoardCmd(size=20).build_request()
    assert req[10:12] == b"\x3f\x05"  # cmd 0x053f
    payload = req[12:]
    assert len(payload) == 10
    assert struct.unpack("<B", payload[0:1])[0] == 0  # category
    assert struct.unpack("<B", payload[1:2])[0] == 5  # mode
    assert payload[9] == 20  # size
    assert req[6:8] == struct.pack("<H", len(payload) + 2)


def test_top_board_parse() -> None:
    body = struct.pack("<B", 1)
    for _ in CATEGORIES:
        body += struct.pack("<B6sff", 1, b"600519", 10.0, 1.5)
    items = GetTopBoardCmd(size=1).parse_response(body)
    assert len(items) == len(CATEGORIES)
    assert items[0].category == "increase"
    assert items[0].market == 1
    assert items[0].code == "600519"
    assert items[0].price == pytest.approx(10.0)
    assert items[0].value == pytest.approx(1.5)
    assert items[-1].category == CATEGORIES[-1]


def test_volume_profile_request_layout() -> None:
    req = GetVolumeProfileCmd(Market.SH, "600519").build_request()
    assert req[10:12] == b"\x1a\x05"  # cmd 0x051a
    payload = req[12:]
    assert payload == struct.pack("<H6s", 1, b"600519")
    assert req[6:8] == struct.pack("<H", len(payload) + 2)
