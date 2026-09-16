"""指数动量命令（0x051c）。

请求体 8 字节：market(u16)+code(6s)。响应：count(u16) + count 个变长整数（累计）。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..codec.price import get_price
from ..models.enums import Market
from .base import BaseCommand

_MSG_ID = 0x051C


class GetIndexMomentumCmd(BaseCommand[list[int]]):
    """获取指数分时动量（累计值序列）。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code

    def build_request(self) -> bytes:
        payload = struct.pack("<H6s", int(self.market), self.code.encode("utf-8"))
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> list[int]:
        (count,) = unpack_from("<H", body, 0, "index_momentum count")
        pos = 2
        total = 0
        values: list[int] = []
        for _ in range(count):
            diff, pos = get_price(body, pos)
            total += diff
            values.append(total)
        return values
