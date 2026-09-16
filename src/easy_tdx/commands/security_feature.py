"""证券扩展特征命令（0x0452）。

特殊品种涨跌停限制表等。请求体 14 字节：start(u32)+count(u32)+one(u32)+zero(u16)。
响应：count(u16) + count 条 13 字节记录（market(u8)+code(u32)+p1(f32)+p2(f32)）。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..models.feature import SecurityFeature
from .base import BaseCommand

_MSG_ID = 0x0452


class GetSecurityFeatureCmd(BaseCommand[list[SecurityFeature]]):
    """获取证券扩展特征（如特殊品种涨跌停限制）。"""

    def __init__(self, start: int = 0, count: int = 2000, one: int = 1) -> None:
        self.start = start
        self.count = count
        self.one = one

    def build_request(self) -> bytes:
        payload = struct.pack("<IIIH", self.start, self.count, self.one, 0)
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> list[SecurityFeature]:
        (count,) = unpack_from("<H", body, 0, "feature452 count")
        pos = 2
        items: list[SecurityFeature] = []
        for _ in range(count):
            market = body[pos]
            (code_num,) = struct.unpack_from("<I", body, pos + 1)
            (p1,) = struct.unpack_from("<f", body, pos + 5)
            (p2,) = struct.unpack_from("<f", body, pos + 9)
            items.append(
                SecurityFeature(
                    market=market,
                    code=f"{code_num:06d}",
                    p1=p1,
                    p2=p2,
                    _raw=body[pos : pos + 13],
                )
            )
            pos += 13
        return items
