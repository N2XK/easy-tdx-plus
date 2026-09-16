"""扩展市场商品列表命令（0x2562）。"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..._binary import require_bytes, unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand

_MSG_ID = 0x2562
_MAX_COUNT = 1000
_RECORD_SIZE = 48
_RECORD_FMT = "<H23sHIBfffHH"


@dataclass(frozen=True)
class GoodsItem:
    """扩展市场商品信息。"""

    name: str
    category: int
    u: int
    index: int
    switch: int
    code: list[float]
    c1: int
    c2: int


class GoodsListCmd(BaseCommand[list[GoodsItem]]):
    """获取扩展市场（期货/期权等）商品列表。

    Args:
        market: 扩展市场代码（ExMarket 枚举值）。
        start: 起始偏移（默认 0）。
        count: 请求数量（最大 1000，默认 600）。
    """

    def __init__(self, market: int, start: int = 0, count: int = 600) -> None:
        if count > _MAX_COUNT:
            raise ValueError(f"count 不能超过 {_MAX_COUNT}，当前: {count}")
        self.market = market
        self.start = start
        self.count = count
        self.total: int = 0

    def build_request(self) -> bytes:
        body = struct.pack("<HII", self.market, self.start, self.count)
        return build_mac_request(_MSG_ID, body)

    def parse_response(self, body: bytes) -> list[GoodsItem]:
        require_bytes(body, 0, 2, "GoodsListCmd header")
        (total,) = unpack_from("<H", body, 0, "GoodsListCmd total")
        self.total = total
        items: list[GoodsItem] = []
        for i in range(total):
            offset = 2 + i * _RECORD_SIZE
            require_bytes(body, offset, _RECORD_SIZE, f"GoodsListCmd record[{i}]")
            category, raw_name, u, index, switch, v1, v2, v3, c1, c2 = unpack_from(
                _RECORD_FMT,
                body,
                offset,
                f"GoodsListCmd record[{i}]",
            )
            name = raw_name.decode("gbk", errors="replace").rstrip("\x00")
            items.append(
                GoodsItem(
                    name=name,
                    category=category,
                    u=u,
                    index=index,
                    switch=switch,
                    code=[v1, v2, v3],
                    c1=c1,
                    c2=c2,
                )
            )
        return items
