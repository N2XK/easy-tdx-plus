"""加密行情命令（0x0547）。

请求体：count(u16) + count×[market(u8)+code(6s)+0x56DA(u16)+2(u16)]。
响应体逐字节 XOR 0x93 后解析：count(u16) + 每条含五档盘口与内外盘等字段。
单次最多 100 只。
"""

from __future__ import annotations

import struct

from .._binary import unpack_from
from ..codec.price import get_price
from ..models.enums import Market
from ..models.feature import EncryptedQuote
from .base import BaseCommand

_MSG_ID = 0x0547
_MAX_CODES = 100


class GetQuotesEncryptCmd(BaseCommand[list[EncryptedQuote]]):
    """批量加密行情（最多 100 只，含完整五档）。"""

    def __init__(self, stocks: list[tuple[Market, str]]) -> None:
        if not stocks:
            raise ValueError("stocks 不能为空")
        if len(stocks) > _MAX_CODES:
            raise ValueError(f"单次最多查询 {_MAX_CODES} 只股票")
        self.stocks = stocks

    def build_request(self) -> bytes:
        payload = bytearray(struct.pack("<H", len(self.stocks)))
        for market, code in self.stocks:
            payload.extend(struct.pack("<B6sHH", int(market), code.encode("utf-8"), 22234, 2))
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", _MSG_ID) + bytes(payload)

    def parse_response(self, body: bytes) -> list[EncryptedQuote]:
        raw = bytes(b ^ 0x93 for b in body)
        (count,) = unpack_from("<H", raw, 0, "quotes_encrypt count")
        pos = 2
        items: list[EncryptedQuote] = []
        for _ in range(count):
            market = raw[pos]
            code = raw[pos + 1 : pos + 7].decode("gbk", errors="replace").rstrip("\x00")
            active = struct.unpack_from("<H", raw, pos + 7)[0]
            pos += 9
            close_raw, pos = get_price(raw, pos)
            pre_diff, pos = get_price(raw, pos)
            open_diff, pos = get_price(raw, pos)
            high_diff, pos = get_price(raw, pos)
            low_diff, pos = get_price(raw, pos)
            pos += 4  # time
            _, pos = get_price(raw, pos)
            vol, pos = get_price(raw, pos)
            cur_vol, pos = get_price(raw, pos)
            (amount,) = struct.unpack_from("<f", raw, pos)
            pos += 4
            in_vol, pos = get_price(raw, pos)
            out_vol, pos = get_price(raw, pos)
            s_amount, pos = get_price(raw, pos)
            open_amount, pos = get_price(raw, pos)
            bids: list[tuple[float, int]] = []
            asks: list[tuple[float, int]] = []
            for _ in range(5):
                bid_diff, pos = get_price(raw, pos)
                ask_diff, pos = get_price(raw, pos)
                bv, pos = get_price(raw, pos)
                av, pos = get_price(raw, pos)
                bids.append(((close_raw + bid_diff) / 100.0, bv))
                asks.append(((close_raw + ask_diff) / 100.0, av))
            pos += 10  # tail
            for _ in range(6):
                for _ in range(4):
                    _, pos = get_price(raw, pos)
            items.append(
                EncryptedQuote(
                    market=market,
                    code=code,
                    active=active,
                    close=close_raw / 100.0,
                    pre_close=(close_raw + pre_diff) / 100.0,
                    open=(close_raw + open_diff) / 100.0,
                    high=(close_raw + high_diff) / 100.0,
                    low=(close_raw + low_diff) / 100.0,
                    vol=vol,
                    cur_vol=cur_vol,
                    amount=float(amount),
                    in_vol=in_vol,
                    out_vol=out_vol,
                    s_amount=s_amount,
                    open_amount=open_amount,
                    bids=bids,
                    asks=asks,
                )
            )
        return items
