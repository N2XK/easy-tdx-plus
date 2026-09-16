"""指数概况命令（0x051d）。

请求体 12 字节：market(u16)+code(6s)+zero(u32)。
响应为变长字段：委托条数、市场、代码、活跃度、若干变长价格、成交额(f32)、
上涨/下跌家数、委托分布明细。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..codec.price import get_price
from ..models.enums import Market
from ..models.feature import IndexInfo, IndexInfoOrder
from .base import BaseCommand

_MSG_ID = 0x051D


def _format_server_time(raw: int) -> str:
    hours, fractional_hour = divmod(raw, 1_000_000)
    total_millis = fractional_hour * 3600 // 1000
    minutes, remainder = divmod(total_millis, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class GetIndexInfoCmd(BaseCommand[IndexInfo]):
    """获取指数概况（含涨跌家数与委托分布）。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code

    def build_request(self) -> bytes:
        payload = struct.pack("<H6sI", int(self.market), self.code.encode("utf-8"), 0)
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> IndexInfo:
        (order_count,), pos = unpack_from("<I", body, 0, "index_info order_count"), 4
        market = body[pos]
        pos += 1
        code = body[pos : pos + 6].decode("utf-8", errors="replace").rstrip("\x00")
        pos += 6
        (active,) = unpack_from("<H", body, pos, "index_info active")
        pos += 2

        close_raw, pos = get_price(body, pos)
        pre_close_diff, pos = get_price(body, pos)
        open_diff, pos = get_price(body, pos)
        high_diff, pos = get_price(body, pos)
        low_diff, pos = get_price(body, pos)
        server_time_raw, pos = get_price(body, pos)
        after_hour, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        cur_vol, pos = get_price(body, pos)
        (amount,) = struct.unpack_from("<f", body, pos)
        pos += 4
        # 11 个未命名变长字段
        for _ in range(2):
            _, pos = get_price(body, pos)
        open_amount, pos = get_price(body, pos)
        for _ in range(3):
            _, pos = get_price(body, pos)
        up_count, pos = get_price(body, pos)
        down_count, pos = get_price(body, pos)
        for _ in range(10):
            _, pos = get_price(body, pos)

        last_price = 0
        orders: list[IndexInfoOrder] = []
        for _ in range(order_count):
            price_raw, pos = get_price(body, pos)
            unknown, pos = get_price(body, pos)
            order_vol, pos = get_price(body, pos)
            last_price += price_raw
            orders.append(IndexInfoOrder(price=last_price / 100.0, unknown=unknown, vol=order_vol))

        return IndexInfo(
            market=market,
            code=code,
            active=active,
            close=close_raw / 100.0,
            pre_close=(close_raw + pre_close_diff) / 100.0,
            diff=-pre_close_diff / 100.0,
            open=(close_raw + open_diff) / 100.0,
            high=(close_raw + high_diff) / 100.0,
            low=(close_raw + low_diff) / 100.0,
            server_time=_format_server_time(server_time_raw),
            vol=vol,
            cur_vol=cur_vol,
            amount=float(amount),
            open_amount=open_amount,
            up_count=up_count,
            down_count=down_count,
            orders=orders,
            _raw=body,
        )
