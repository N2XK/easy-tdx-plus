"""MAC 单日分时图命令（0x122D）。

获取单只股票某日的分时数据。
"""

import struct
from datetime import date, time

from ..._binary import unpack_from
from ...codec.datetime_ import coerce_date
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import MacTick, MacTickChart

_MSG_ID = 0x122D


class SymbolTickChartCmd(BaseCommand[MacTickChart]):
    """获取单日分时图。

    Args:
        market:    市场代码。
        code:      6 位股票代码。
        query_date: 查询日期（None 或 date(0,0,0) 表示今天）。
    """

    def __init__(
        self,
        market: int,
        code: str,
        query_date: date | int | str | None = None,
    ) -> None:
        self._market = market
        self._code = code
        qd = coerce_date(query_date)
        if qd is not None:
            self._ymd = qd.year * 10000 + qd.month * 100 + qd.day
        else:
            self._ymd = 0

    def build_request(self) -> bytes:
        body = struct.pack(
            "<H22sI5H",
            self._market,
            self._code.encode("gbk"),
            self._ymd,
            1,
            0,
            0,
            0,
            0,
        )
        return build_mac_request(_MSG_ID, body)

    def parse_response(self, body: bytes) -> MacTickChart:
        # 头部: market(2) + code(22) + query_date(4) + reserved(1) + ref_price(4) + count(2)
        (market, code_raw, query_date, reserved, ref_price, count) = unpack_from(
            "<H22sIBfH", body, 0, "tick_chart header"
        )

        ticks: list[MacTick] = []
        for i in range(count):
            offset = 35 + i * 18
            (minutes, price, avg, vol, momentum) = unpack_from(
                "<HffIf", body, offset, f"tick_chart tick[{i}]"
            )
            ticks.append(
                MacTick(
                    time=time(minutes // 60 % 24, minutes % 60),
                    price=price,
                    avg=avg,
                    vol=vol,
                    momentum=momentum,
                )
            )

        # 尾部元数据
        tail_offset = 35 + count * 18
        (
            name_raw,
            _decimal,
            _category,
            _vol_unit,
            _date_raw,
            _time_raw,
            pre_close,
            open,
            high,
            low,
            close,
            _momentum_tail,
            vol,
            amount,
            _tail_pad2,
            turnover,
            avg_tail,
            _industry,
        ) = unpack_from("<44sBHf5x2I5ffIf12s2fI", body, tail_offset, "tick_chart tail")

        return MacTickChart(
            market=market,
            code=code_raw.decode("gbk", errors="ignore").replace("\x00", ""),
            name=name_raw.decode("gbk", errors="ignore").replace("\x00", ""),
            pre_close=pre_close,
            open=open,
            high=high,
            low=low,
            close=close,
            vol=int(vol),
            amount=amount,
            turnover=turnover,
            avg=avg_tail,
            charts=ticks,
        )
