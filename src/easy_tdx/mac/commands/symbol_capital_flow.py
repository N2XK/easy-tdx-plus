"""个股资金流向查询（0x1218 head=2）。"""

import json
import struct

from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import CapitalFlowData

# head=2 用于区分 symbol_capital_flow 与 symbol_belong_board (head=1)
_HEAD_FLAG = 2


def _to_float(value: object) -> float:
    """Safely convert JSON value to float."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return 0.0


class SymbolCapitalFlowCmd(BaseCommand[CapitalFlowData | None]):
    """查询个股资金流向（0x1218 head=2, Query=Stock_ZJLX）。

    响应为两段 JSON（字段口径同 gotdx ``mac_capital_flow.go``）：
    今日 ``[主力买, 主力卖, 散户买, 散户卖]``；
    5 日 ``[主力买, 主力卖, 超大单净, 大单净, 中单净, 小单净]``。

    Parameters
    ----------
    market : int
        市场代码。
    code : str
        证券代码。
    """

    def __init__(self, market: int, code: str) -> None:
        self._market = market
        self._code = code

    def build_request(self) -> bytes:
        # H:market, 8s:code padded with spaces, 16s:padding, 21s:"Stock_ZJLX"
        body = struct.pack(
            "<H8s16x21s",
            self._market,
            self._code.encode("gbk"),
            b"Stock_ZJLX",
        )
        return build_mac_request(0x1218, body, head_flag=_HEAD_FLAG)

    def parse_response(self, body: bytes) -> CapitalFlowData | None:
        # 响应头: H:market, 12s:query_info, 5x padding, 8s:ext = 27 bytes
        if len(body) < 27:
            return None

        json_bytes = body[27:]
        python_list: list[list[object]] = json.loads(json_bytes.decode("gbk"))

        if len(python_list) < 2:
            return None

        today_data = python_list[0]
        five_days_data = python_list[1]

        def g(seq: list[object], i: int) -> float:
            return _to_float(seq[i]) if len(seq) > i else 0.0

        # 今日: [主力买, 主力卖, 散户买, 散户卖]
        main_in, main_out = g(today_data, 0), g(today_data, 1)
        retail_in, retail_out = g(today_data, 2), g(today_data, 3)

        # 5 日: [主力买, 主力卖, 超大单净, 大单净, 中单净, 小单净]
        main_buy_5d, main_sell_5d = g(five_days_data, 0), g(five_days_data, 1)

        return CapitalFlowData(
            date="",
            main_in=main_in,
            main_out=main_out,
            main_net=main_in - main_out,
            small_in=retail_in,
            small_out=retail_out,
            small_net=retail_in - retail_out,
            main_buy_5d=main_buy_5d,
            main_sell_5d=main_sell_5d,
            main_net_5d=main_buy_5d - main_sell_5d,
            super_large_net_5d=g(five_days_data, 2),
            large_net_5d=g(five_days_data, 3),
            medium_net_5d=g(five_days_data, 4),
            small_net_5d=g(five_days_data, 5),
        )
