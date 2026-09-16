"""MAC 逐笔成交命令（0x122F）。

获取单只股票的逐笔成交数据。
"""

import struct
from datetime import date, time

from ..._binary import unpack_from
from ...codec.datetime_ import coerce_date
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import MacTransaction

_MSG_ID = 0x122F


class SymbolTransactionCmd(BaseCommand[list[MacTransaction]]):
    """获取逐笔成交数据。

    Args:
        market:     市场代码。
        code:       6 位股票代码。
        query_date: 查询日期（None 表示今天）。
        start:      起始偏移。
        count:      返回条数。
    """

    def __init__(
        self,
        market: int,
        code: str,
        query_date: date | int | str | None = None,
        start: int = 0,
        count: int = 1000,
    ) -> None:
        self._market = market
        self._code = code
        qd = coerce_date(query_date)
        if qd is not None:
            self._ymd = qd.year * 10000 + qd.month * 100 + qd.day
        else:
            self._ymd = 0
        self._start = start
        self._count = count

    def build_request(self) -> bytes:
        body = struct.pack(
            "<H22sIIH10x",
            self._market,
            self._code.encode("gbk"),
            self._ymd,
            self._start,
            self._count,
        )
        return build_mac_request(_MSG_ID, body)

    def parse_response(self, body: bytes) -> list[MacTransaction]:
        # 头部: market(2) + code(22) + query_date(4) + flag(1) + count(2) + start(4) + total(4) = 39
        (count,) = unpack_from("<H", body, 29, "transaction count")

        results: list[MacTransaction] = []
        for i in range(count):
            offset = 39 + i * 18
            (time_sec, price, volume, trade_count, bs_flag) = unpack_from(
                "<IfIIH", body, offset, f"transaction item[{i}]"
            )
            results.append(
                MacTransaction(
                    time=time(time_sec // 3600, time_sec % 3600 // 60, time_sec % 60),
                    price=price,
                    vol=volume,
                    trade_count=trade_count,
                    bs_flag=bs_flag,
                )
            )

        return results
