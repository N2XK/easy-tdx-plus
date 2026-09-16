"""板块成分报价查询（0x122C）。

响应格式与 symbol_quotes (0x122B) 相同：20 字节位图 + 总数 + 行数 + N 条记录。
每条记录：market(2) + code(22) + name(44) + active_fields × 4 字节。
"""

import struct

from ..._binary import unpack_from
from ...codec.bitmap import (
    FIELD_POSTPROCESS,
    Fields,
    PresetField,
    build_bitmap,
    get_active_fields,
)
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..enums import FilterType, SortOrder, SortType
from ..models import MacQuoteField


class BoardMembersQuotesCmd(BaseCommand[list[MacQuoteField]]):
    """查询板块成分股报价。

    Parameters
    ----------
    board_code : int
        板块代码（如 int("881001")）。
    sort_type : SortType
        排序字段。
    start : int
        起始偏移量。
    page_size : int
        每页数量。
    sort_order : SortOrder
        排序方向。
    fields : Fields
        请求的字段集合。
    exclude_flags : list[FilterType] | None
        排除条件列表（如排除科创板、创业板等）。
    """

    def __init__(
        self,
        board_code: int,
        sort_type: SortType = SortType.CHANGE_PCT,
        start: int = 0,
        page_size: int = 80,
        sort_order: SortOrder = SortOrder.NONE,
        fields: Fields = PresetField.NONE,
        exclude_flags: list[FilterType] | None = None,
    ) -> None:
        self._board_code = board_code
        self._sort_type = sort_type
        self._start = start
        self._page_size = page_size
        self._sort_order = sort_order
        self._fields = fields
        self._exclude_flags = exclude_flags or []

    def build_request(self) -> bytes:
        # I:board_code, 9x padding, H:sort_type, I:start, H:page_size, B:sort_order, B:pad
        body = struct.pack(
            "<I9xHIHBB",
            self._board_code,
            int(self._sort_type),
            self._start,
            self._page_size,
            int(self._sort_order),
            0,
        )

        # 16 字节字段位图
        bitmap = build_bitmap(self._fields)
        body += bytes(bitmap[:16])

        # 4 字节控制区: byte0=盘口, byte1=排除位, byte2=日内, byte3=控制(CTRL_EXTENDED=1)
        b1 = sum(f.value for f in self._exclude_flags)
        body += struct.pack("<BBBB", 0, b1, 0, 1)

        return build_mac_request(0x122C, body)

    def parse_response(self, body: bytes) -> list[MacQuoteField]:
        # 响应位图（20 字节）
        resp_bitmap = body[:20]

        total, row_count = unpack_from("<IH", body, 20, "board_members header")

        active_fields = get_active_fields(resp_bitmap[:16])
        field_count = len(active_fields)

        # 每行: market(2) + code(22) + name(44) = 68 + field_count * 4
        row_len = 68 + field_count * 4

        results: list[MacQuoteField] = []
        for i in range(row_count):
            row_start = 26 + i * row_len
            market_raw = unpack_from("<H", body, row_start, f"board_members row[{i}] market")[0]
            code_raw = body[row_start + 2 : row_start + 24]
            name_raw = body[row_start + 24 : row_start + 68]

            fields_dict: dict[str, object] = {}
            for idx, (field_bit, fmt) in enumerate(active_fields):
                val_bytes = body[row_start + 68 + idx * 4 : row_start + 68 + (idx + 1) * 4]
                if len(val_bytes) < 4:
                    break
                (value,) = struct.unpack(fmt, val_bytes)
                post_fn = FIELD_POSTPROCESS.get(field_bit.value)
                if post_fn is not None:
                    value = post_fn(value, market_raw)  # type: ignore[operator]
                fields_dict[field_bit.field_name] = value

            results.append(
                MacQuoteField(
                    market=market_raw,
                    code=code_raw.decode("gbk", errors="replace").rstrip("\x00"),
                    name=name_raw.decode("gbk", errors="replace").rstrip("\x00"),
                    fields=fields_dict,
                )
            )

        return results
