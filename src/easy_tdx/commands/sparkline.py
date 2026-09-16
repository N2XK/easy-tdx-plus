"""小走势图命令（0x0fd1）。

请求体（39 字节）：
  market(u16) + code(22s) + selector(u16) + window(u16) + 11 字节保留
响应体：
  market(u16) + code(22s) + selector_echo(u16) + (u16) + 6 字节保留 +
  max_count(u16) + base_price(f32) + count(u16) + count 个 price(f32)
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..models.enums import Market
from ..models.timeseries import SparklineSeries
from .base import BaseCommand

_MSG_ID = 0x0FD1


class GetSparklineCmd(BaseCommand[SparklineSeries]):
    """获取单标的小走势图（轻量价格序列）。"""

    def __init__(self, market: Market, code: str, selector: int = 1, window: int = 20) -> None:
        self.market = market
        self.code = code
        self.selector = selector
        self.window = window

    def build_request(self) -> bytes:
        payload = (
            struct.pack("<H", int(self.market))
            + self.code.encode("utf-8").ljust(22, b"\x00")
            + struct.pack("<HH", self.selector, self.window)
            + b"\x00" * 11
        )
        header = struct.pack("<HIHH", 0x010C, 0x01010008, len(payload), len(payload))
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> SparklineSeries:
        market, code_raw = unpack_from("<H22s", body, 0, "sparkline header")
        selector = unpack_from("<H", body, 24, "sparkline selector")[0]
        max_count = unpack_from("<H", body, 34, "sparkline max_count")[0]
        (base_price,) = unpack_from("<f", body, 36, "sparkline base_price")
        (count,) = unpack_from("<H", body, 40, "sparkline count")
        prices = [
            unpack_from("<f", body, 42 + i * 4, f"sparkline price[{i}]")[0] for i in range(count)
        ]
        return SparklineSeries(
            market=market,
            code=code_raw.decode("utf-8").rstrip("\x00"),
            selector=selector,
            max_count=max_count,
            base_price=base_price,
            prices=prices,
            _raw=body,
        )
