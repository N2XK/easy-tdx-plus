"""集合竞价过程快照命令（0x056a）。

按证券（可选日期）读取当日或历史的集合竞价过程快照，秒级一条，
含虚拟匹配价、匹配量、未匹配量。

请求体 28 字节：market(u8)+zero(u8)+code(6s)+date(u32)+selector(u32)
+zero(u32)+start(u32)+count(u32)。
响应：count(u16) + count 条 16 字节记录
（minute_of_day(u16)+price(f32)+matched(u32)+unmatched(i32)+zero(u8)+second(u8)）。
"""

from __future__ import annotations

import struct
from datetime import time

from .._binary import unpack_from
from ..models.auction import AuctionPoint
from ..models.enums import Market
from .base import BaseCommand

_MSG_ID = 0x056A
_RECORD_SIZE = 16
_DEFAULT_SELECTOR = 3
_DEFAULT_COUNT = 500


class GetAuctionSeriesCmd(BaseCommand[list[AuctionPoint]]):
    """获取集合竞价过程快照（0x056a）。"""

    def __init__(
        self,
        market: Market,
        code: str,
        date: int | None = None,
        selector: int = _DEFAULT_SELECTOR,
        start: int = 0,
        count: int = _DEFAULT_COUNT,
    ) -> None:
        self.market = market
        self.code = code
        self.date = int(date) if date else 0
        self.selector = selector
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        payload = struct.pack(
            "<BB6sIIIII",
            int(self.market),
            0,
            self.code.encode("utf-8"),
            self.date,
            self.selector,
            0,
            self.start,
            self.count,
        )
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> list[AuctionPoint]:
        (count,) = unpack_from("<H", body, 0, "auction series count")
        points: list[AuctionPoint] = []
        pos = 2
        for _ in range(count):
            if pos + _RECORD_SIZE > len(body):
                break
            minute, price, matched, unmatched = struct.unpack_from("<HfIi", body, pos)
            second = body[pos + 15]
            points.append(
                AuctionPoint(
                    time=time(minute // 60, minute % 60, second),
                    price=price,
                    matched=int(matched),
                    unmatched=int(unmatched),
                )
            )
            pos += _RECORD_SIZE
        return points
