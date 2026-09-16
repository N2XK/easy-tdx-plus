"""分类代码表命令（0x124A）。

实测响应：头部 8 字节 + N 条 35 字节记录，记录形如
``flag(1) + code(6,ASCII) + name(8,GBK) + 8B + tag(ASCII) + tail``，
内容为通达信板块/分类指数代码表（395001=主板Ａ股/tag=ZBAG 等）。

注：小 count（如 5/100）时服务端只回显头部、不带记录；大 count 才返回整表。
协议细节部分未完全确证，记录保留 ``raw`` 供核对。
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

    def build_request(self) -> bytes:
        # I:offset, I:count, 5 bytes padding
        body = struct.pack("<II5x", self._offset, self._count)
        return build_mac_request(0x124A, body)

    def parse_response(self, body: bytes) -> list[CategoryCodeItem]:
        if len(body) < 8:
            return []
        (returned,) = unpack_from("<I", body, 4, "category code count")
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
