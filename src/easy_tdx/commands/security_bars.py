"""获取 K 线数据命令（支持全部周期）。"""

import struct

from .._binary import unpack_from
from ..codec.datetime_ import get_datetime
from ..codec.price import get_price
from ..codec.volume import get_volume
from ..exceptions import TdxDecodeError
from ..models.bar import SecurityBar
from ..models.enums import KlineCategory, Market
from .base import BaseCommand


def _check_record_count(body: bytes, ret_count: int) -> None:
    """校验响应体是否可能容纳声明的记录数。

    部分通达信服务器（多为纯报价节点）不支持标准协议 K 线，会返回
    一个 2 字节的残缺响应（例如 ``2003``）而不带任何 K 线记录，导致后续
    解码时抛出难以理解的 “数据不足” 错误。这里提前给出明确提示。
    """
    if ret_count > 0 and len(body) < 2 + ret_count:
        raise TdxDecodeError(
            f"标准协议 K 线响应异常：声明 {ret_count} 条记录但响应体仅 {len(body)} 字节，"
            "当前服务器可能不支持该命令，请更换行情服务器"
        )


class GetSecurityBarsCmd(BaseCommand[list[SecurityBar]]):
    """获取指定股票的 K 线数据。

    Args:
        market:   市场（SH/SZ）
        code:     6位股票代码（字符串）
        category: K线周期
        start:    起始行（0 = 最新；分页时递增）
        count:    返回条数（最多 800）
    """

    def __init__(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.category = category
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # Header (12 bytes) + Payload (28 bytes) = 40 bytes
        return struct.pack(
            "<HIHHHH6sHHHHIIH",
            0x010C,
            0x01016408,
            0x001C,
            0x001C,
            0x052D,
            int(self.market),
            self.code,
            int(self.category),
            1,
            self.start,
            self.count,
            0,
            0,
            0,
        )

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        (ret_count,) = unpack_from("<H", body, 0, "security_bars header")
        _check_record_count(body, ret_count)
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(self.category)

        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)

            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)

            # 差分还原（与 pytdx 完全一致）
            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff

            bars.append(
                SecurityBar(
                    open=open_abs / 1000.0,
                    close=close_abs / 1000.0,
                    high=high_abs / 1000.0,
                    low=low_abs / 1000.0,
                    vol=vol,
                    amount=amount,
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    _raw=body[record_start:pos],
                )
            )

        return bars


class GetIndexBarsCmd(GetSecurityBarsCmd):
    """获取指数 K 线。

    请求格式与股票 K 线相同，但响应每条记录在 vol+amt 后多 4 字节
    （上涨家数 uint16 + 下跌家数 uint16），必须跳过否则后续记录错位。
    """

    def parse_response(self, body: bytes) -> list[SecurityBar]:
        (ret_count,) = unpack_from("<H", body, 0, "security_bars header")
        _check_record_count(body, ret_count)
        pos = 2
        bars: list[SecurityBar] = []
        pre_diff_base = 0
        cat = int(self.category)

        for _ in range(ret_count):
            record_start = pos
            year, month, day, hour, minute, pos = get_datetime(cat, body, pos)

            open_diff, pos = get_price(body, pos)
            close_diff, pos = get_price(body, pos)
            high_diff, pos = get_price(body, pos)
            low_diff, pos = get_price(body, pos)

            vol, pos = get_volume(body, pos)
            amount, pos = get_volume(body, pos)

            # 指数记录额外 4 字节：上涨家数 + 下跌家数（各 uint16 LE）
            pos += 4

            open_abs = open_diff + pre_diff_base
            close_abs = open_abs + close_diff
            high_abs = open_abs + high_diff
            low_abs = open_abs + low_diff
            pre_diff_base = open_abs + close_diff

            bars.append(
                SecurityBar(
                    open=open_abs / 1000.0,
                    close=close_abs / 1000.0,
                    high=high_abs / 1000.0,
                    low=low_abs / 1000.0,
                    vol=vol,
                    amount=amount,
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    _raw=body[record_start:pos],
                )
            )

        return bars
