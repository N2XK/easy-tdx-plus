"""分时缩略采样命令（0x254D）。"""

from __future__ import annotations

import struct

from ..._binary import require_bytes, unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand

_MSG_ID = 0x254D
_CODE_LEN = 22
_RESPONSE_HEADER_SIZE = 42  # H(2) + 22s(22) + 9*H(18) = 42


class ChartSamplingCmd(BaseCommand[list[float]]):
    """获取分时缩略采样价格点（0x254D，**MAC-EX / 7727 专用**）。

    - A 股端口（7709）不响应此命令（A 股请用 0x122D，见 ``MacClient.get_chart_sampling``）；
    - 采样间隔约 **4 分钟**、点数上限约 **100**（美股完整交易日实测 100 点）；
    - **无当前交易时段数据时返回空**（如盘前，或 HK/期货当日未开盘）。

    Args:
        market: 扩展市场代码（ExMarket 枚举值）。
        code: 证券代码（GBK 编码）。
    """

    def __init__(self, market: int, code: str) -> None:
        self.market = market
        self.code = code

    def build_request(self) -> bytes:
        raw_code = self.code.encode("gbk")
        padded = (raw_code + b"\x00" * _CODE_LEN)[:_CODE_LEN]
        body = struct.pack("<H22sHH9x", self.market, padded, 1, 20)
        return build_mac_request(_MSG_ID, body)

    def parse_response(self, body: bytes) -> list[float]:
        if len(body) < _RESPONSE_HEADER_SIZE:
            return []
        require_bytes(body, 0, _RESPONSE_HEADER_SIZE, "ChartSamplingCmd header")
        (count,) = unpack_from("<H", body, 40, "chart_sampling count")
        prices: list[float] = []
        for i in range(count):
            pos = _RESPONSE_HEADER_SIZE + i * 4
            require_bytes(body, pos, 4, f"ChartSamplingCmd price[{i}]")
            (p,) = unpack_from("<f", body, pos, f"chart_sampling price[{i}]")
            prices.append(p)
        return prices
