"""成交分布命令（0x051a）。

请求体 8 字节：market(u16)+code(6s)，长度字段 = payload+2。
响应含现价/昨收/高低、内外盘、三档买卖盘、以及成交分布明细
（累计价格档位 + 该档总量/主买/主卖）。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..codec.price import get_price
from ..models.enums import Market
from ..models.feature import VolumeProfile, VolumeProfileItem
from .base import BaseCommand

_MSG_ID = 0x051A


def _format_server_time(raw: int) -> str:
    hours, fractional_hour = divmod(raw, 1_000_000)
    total_millis = fractional_hour * 3600 // 1000
    minutes, remainder = divmod(total_millis, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class GetVolumeProfileCmd(BaseCommand[VolumeProfile]):
    """获取个股成交分布（Volume Profile）。"""

    def __init__(self, market: Market, code: str) -> None:
        self.market = market
        self.code = code

    def build_request(self) -> bytes:
        payload = struct.pack("<H6s", int(self.market), self.code.encode("utf-8"))
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + payload

    def parse_response(self, body: bytes) -> VolumeProfile:
        (count,) = unpack_from("<H", body, 0, "volume_profile count")
        market = body[2]
        code = body[3:9].decode("utf-8", errors="replace").rstrip("\x00")
        (active,) = unpack_from("<H", body, 9, "volume_profile active")
        pos = 11

        base_price, pos = get_price(body, pos)
        pre_close_diff, pos = get_price(body, pos)
        open_diff, pos = get_price(body, pos)
        high_diff, pos = get_price(body, pos)
        low_diff, pos = get_price(body, pos)
        server_time_raw, pos = get_price(body, pos)
        neg_price_raw, pos = get_price(body, pos)
        vol, pos = get_price(body, pos)
        cur_vol, pos = get_price(body, pos)
        (amount,) = struct.unpack_from("<f", body, pos)
        pos += 4
        in_vol, pos = get_price(body, pos)
        out_vol, pos = get_price(body, pos)
        s_amount, pos = get_price(body, pos)
        open_amount, pos = get_price(body, pos)

        bids: list[tuple[float, int]] = []
        asks: list[tuple[float, int]] = []
        for _ in range(3):
            bid_diff, pos = get_price(body, pos)
            ask_diff, pos = get_price(body, pos)
            bv, pos = get_price(body, pos)
            av, pos = get_price(body, pos)
            bids.append(((base_price + bid_diff) / 100.0, bv))
            asks.append(((base_price + ask_diff) / 100.0, av))

        pos += 2  # unknown u16

        profile_price = 0
        profiles: list[VolumeProfileItem] = []
        for _ in range(count):
            price_delta, pos = get_price(body, pos)
            item_vol, pos = get_price(body, pos)
            buy, pos = get_price(body, pos)
            sell, pos = get_price(body, pos)
            profile_price += price_delta
            profiles.append(
                VolumeProfileItem(price=profile_price / 100.0, vol=item_vol, buy=buy, sell=sell)
            )

        return VolumeProfile(
            market=market,
            code=code,
            active=active,
            close=base_price / 100.0,
            pre_close=(base_price + pre_close_diff) / 100.0,
            open=(base_price + open_diff) / 100.0,
            high=(base_price + high_diff) / 100.0,
            low=(base_price + low_diff) / 100.0,
            server_time=_format_server_time(server_time_raw),
            neg_price=neg_price_raw / 100.0,
            vol=vol,
            cur_vol=cur_vol,
            amount=float(amount),
            in_vol=in_vol,
            out_vol=out_vol,
            s_amount=s_amount,
            open_amount=open_amount,
            bids=bids,
            asks=asks,
            profiles=profiles,
            _raw=body,
        )
