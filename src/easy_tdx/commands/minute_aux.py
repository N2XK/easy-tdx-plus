"""分时副图命令（0x051b）。

口径（selector）：
  0x00  买卖力道（buy_sell_strength）—— 每点 (买入力道 u8, 卖出力道 u8)
  0x0b  成交对比（volume_comparison）—— 每点 (序列A f32, 序列B f32)

请求体（30 字节）：
  market(u16) + code(6s) + 19 字节保留 + selector(u8) + 2 字节保留
响应体：
  count(u16) + count 个数据点（布局随 selector 而定）
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..models.enums import Market
from ..models.timeseries import MinuteAuxPoint
from .base import BaseCommand

_MSG_ID = 0x051B
_SELECTOR_BUY_SELL = 0x00
_SELECTOR_VOLUME_COMPARE = 0x0B

_SELECTORS: dict[str, int] = {
    "buy_sell_strength": _SELECTOR_BUY_SELL,
    "buy_sell": _SELECTOR_BUY_SELL,
    "commission": _SELECTOR_BUY_SELL,
    "volume_comparison": _SELECTOR_VOLUME_COMPARE,
    "volume_compare": _SELECTOR_VOLUME_COMPARE,
}


def resolve_selector(kind: str | int) -> int:
    """将副图类型（字符串或数字）解析为 selector。"""
    if isinstance(kind, int):
        return kind
    try:
        return _SELECTORS[kind]
    except KeyError as e:
        raise ValueError(f"未知副图类型: {kind!r}") from e


class GetMinuteAuxCmd(BaseCommand[list[MinuteAuxPoint]]):
    """获取分时副图数据（240 点）。"""

    def __init__(self, market: Market, code: str, selector: int) -> None:
        self.market = market
        self.code = code
        self.selector = selector

    def build_request(self) -> bytes:
        payload = (
            struct.pack("<H", int(self.market))
            + self.code.encode("utf-8").ljust(6, b"\x00")
            + b"\x00" * 19
            + bytes([self.selector])
            + b"\x00" * 2
        )
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> list[MinuteAuxPoint]:
        (count,) = unpack_from("<H", body, 0, "minute_aux count")
        points: list[MinuteAuxPoint] = []
        if self.selector == _SELECTOR_VOLUME_COMPARE:
            for i in range(count):
                pos = 2 + i * 8
                a, b = unpack_from("<ff", body, pos, f"minute_aux point[{i}]")
                points.append(MinuteAuxPoint(index=i, series_a=a, series_b=b))
        else:
            for i in range(count):
                pos = 2 + i * 2
                buy = body[pos] if pos < len(body) else 0
                sell = body[pos + 1] if pos + 1 < len(body) else 0
                points.append(MinuteAuxPoint(index=i, buy=buy, sell=sell))
        return points
