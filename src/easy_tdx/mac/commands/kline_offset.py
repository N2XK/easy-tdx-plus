"""K线偏移/分类代码表命令（0x124A）。

协议（对齐 gotdx ``mac_kline_offset.go``，走 EX 帧）：
请求 ``offset(u32)+count(u32)+5x``；响应头部 ``Total(大端 u32)+Returned(小端 u32)``。

实测：小 count（5/100）只回头部、无记录；``count=128000`` 时随后跟
``Returned`` 条 35 字节记录，形如
``flag(1)+code(6,ASCII)+name(8,GBK)+8B+tag(4,ASCII)+tail(8)``，
内容是板块/分类指数代码表（395001=主板Ａ股/tag=ZBAG），每行的 tail 为
偏移/标志元数据（语义未确证，保留 ``raw``）。头部 Total/Returned 可从
返回表 ``df.attrs`` 获取。
"""

import struct

from ..._binary import unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import CategoryCodeItem

_RECORD_SIZE = 35


class KlineOffsetCmd(BaseCommand[list[CategoryCodeItem]]):
    """查询分类代码表（0x124A）。

    Parameters
    ----------
    offset : int
        偏移量（通常为 0）。
    count : int
        请求数量；足够大时返回整表（实测 128000 返回 500 条）。
    """

    def __init__(self, offset: int = 0, count: int = 128000) -> None:
        self._offset = offset
        self._count = count
        self.total: int = 0
        self.returned: int = 0

    def build_request(self) -> bytes:
        # I:offset, I:count, 5 bytes padding
        body = struct.pack("<II5x", self._offset, self._count)
        return build_mac_request(0x124A, body)

    def parse_response(self, body: bytes) -> list[CategoryCodeItem]:
        if len(body) < 8:
            return []
        (self.total,) = unpack_from(">I", body, 0, "kline offset total")
        (returned,) = unpack_from("<I", body, 4, "category code count")
        self.returned = int(returned)
        data = body[8:]
        n = min(int(returned), len(data) // _RECORD_SIZE)
        items: list[CategoryCodeItem] = []
        for i in range(n):
            rec = data[i * _RECORD_SIZE : (i + 1) * _RECORD_SIZE]
            flag = rec[0]
            code = rec[1:7].decode("ascii", errors="replace").strip("\x00")
            name = rec[7:15].decode("gbk", errors="replace").rstrip("\x00").strip()
            tail = rec[15:]
            tag = bytes(b for b in tail if 0x20 < b < 0x7F).decode("ascii", errors="ignore")
            items.append(CategoryCodeItem(flag=flag, code=code, name=name, tag=tag, raw=rec))
        return items
