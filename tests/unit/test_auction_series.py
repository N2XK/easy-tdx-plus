"""集合竞价过程快照命令（0x056a）离线测试。"""

from __future__ import annotations

import struct
from datetime import time

from easy_tdx.commands.auction_series import GetAuctionSeriesCmd
from easy_tdx.models.enums import Market


def _body(records: list[tuple[int, float, int, int, int]]) -> bytes:
    out = struct.pack("<H", len(records))
    for minute, price, matched, unmatched, second in records:
        out += struct.pack("<HfIiBB", minute, price, matched, unmatched, 0, second)
    return out


def test_parse_auction_series() -> None:
    # 首个记录取自真实采样：09:15:00 价 11.82、匹配 36、未匹配 94
    body = _body(
        [
            (9 * 60 + 15, 11.82, 36, 94, 0),
            (9 * 60 + 15, 11.81, 370, -90, 9),
        ]
    )
    points = GetAuctionSeriesCmd(Market.SZ, "000001").parse_response(body)
    assert len(points) == 2
    assert points[0].time == time(9, 15, 0)
    assert abs(points[0].price - 11.82) < 1e-4
    assert points[0].matched == 36 and points[0].unmatched == 94
    assert points[1].time == time(9, 15, 9)
    assert points[1].unmatched == -90


def test_parse_auction_series_truncated_is_safe() -> None:
    body = struct.pack("<H", 5) + struct.pack("<HfIiBB", 555, 1.0, 1, 1, 0, 0)
    assert len(GetAuctionSeriesCmd(Market.SZ, "000001").parse_response(body)) == 1


def test_build_request_layout() -> None:
    req = GetAuctionSeriesCmd(Market.SZ, "000001", date=20260814).build_request()
    assert len(req) == 10 + 2 + 28
    assert req[10:12] == struct.pack("<H", 0x056A)
    # 帧长字段 = payload + 2
    assert struct.unpack_from("<H", req, 6)[0] == 30
    payload = req[12:]
    assert payload[0] == int(Market.SZ) and payload[1] == 0
    assert payload[2:8] == b"000001"
    assert struct.unpack_from("<I", payload, 8)[0] == 20260814
