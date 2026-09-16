"""扩展市场表格命令（0x2422）。

请求体 126 字节：start(u32)+zero(u32)+token(16s)+reserved(85s)+mode(u8)+pad(16s)。
响应：start(u32)@35、count(u32)@161、content(GBK 文本)@169。
"""

from __future__ import annotations

import struct

from ..._binary import unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import ExTableChunk

_MSG_TABLE = 0x2422

# 固定 token（来自 gotdx 参考实现）
_TOKEN = bytes(
    [0x00, 0x78, 0x1F, 0x0E, 0x6A, 0x37, 0x44, 0x7B, 0x50, 0x2B, 0x7C, 0x0D, 0x01, 0x40, 0x4C, 0x0A]
)


class GetExTableCmd(BaseCommand[ExTableChunk]):
    """扩展市场表格（0x2422，文本分块）。"""

    _MSG_ID = _MSG_TABLE
    _MODE = 1

    def __init__(self, start: int = 0) -> None:
        self.start = start

    def build_request(self) -> bytes:
        payload = (
            struct.pack("<II", self.start, 0)
            + _TOKEN
            + b"\x00" * 85
            + bytes([self._MODE])
            + b"\x00" * 16
        )
        return build_mac_request(self._MSG_ID, payload, head_flag=0x01)

    def parse_response(self, body: bytes) -> ExTableChunk:
        if len(body) < 169:
            return ExTableChunk(start=0, count=0, content="", _raw=body)
        (start,) = unpack_from("<I", body, 35, "ex_table start")
        (count,) = unpack_from("<I", body, 161, "ex_table count")
        content = body[169:].decode("gbk", errors="replace").rstrip("\x00")
        return ExTableChunk(start=start, count=count, content=content, _raw=body)
