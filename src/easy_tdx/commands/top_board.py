"""排行榜命令（0x053f）。

请求体 10 字节：category(u8)+mode(u8)+reserved(7s)+size(u8)，长度字段 = payload+2。
响应：size(u8) + 9 组榜单 × size 条 15 字节记录
（market(u8)+code(6s)+price(f32)+value(f32)）。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..models.feature import TopBoardItem
from .base import BaseCommand

_MSG_ID = 0x053F

CATEGORIES = (
    "increase",
    "decrease",
    "amplitude",
    "rise_speed",
    "fall_speed",
    "vol_ratio",
    "pos_commission_ratio",
    "neg_commission_ratio",
    "turnover",
)


class GetTopBoardCmd(BaseCommand[list[TopBoardItem]]):
    """获取排行榜（涨幅/跌幅/振幅/涨速/量比/委比/换手 等 9 组）。"""

    def __init__(self, category: int = 0, size: int = 20, mode: int = 5) -> None:
        self.category = category
        self.size = size
        self.mode = mode

    def build_request(self) -> bytes:
        reserved = bytes([0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00])
        payload = struct.pack("<BB7sB", self.category, self.mode, reserved, self.size)
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> list[TopBoardItem]:
        (size,) = unpack_from("<B", body, 0, "top_board size")
        pos = 1
        items: list[TopBoardItem] = []
        for category in CATEGORIES:
            for _ in range(size):
                market = body[pos]
                code = body[pos + 1 : pos + 7].decode("utf-8", errors="replace").rstrip("\x00")
                (price,) = struct.unpack_from("<f", body, pos + 7)
                (value,) = struct.unpack_from("<f", body, pos + 11)
                items.append(
                    TopBoardItem(
                        category=category,
                        market=market,
                        code=code,
                        price=price,
                        value=value,
                        _raw=body[pos : pos + 15],
                    )
                )
                pos += 15
        return items
