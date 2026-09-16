"""MAC EX 扩展行情登录命令（msg_id=0x2454）。

MAC EX 服务器（端口 7727）在数据查询前要求先完成 Login，
否则后续所有命令都会被服务器断开连接。
"""

import struct

from ...commands.base import BaseCommand

_MSG_ID = 0x2454
_HEAD_FLAG = 0x01

# 80 字节 Login body，来自 opentdx 参考实现，已通过实际测试验证。
_LOGIN_BODY = bytes(
    bytearray.fromhex(
        "e5bb1c2fafe52594"
        "1f32c6e5d53dfb41"
        "5b734cc9cdbf0ac9"
        "2021bfdd1eb06d22"
        "d008884c1611cb13"
        "78f6abd824d899d2"
        "1f32c6e5d53dfb41"
        "1f32c6e5d53dfb41"
        "a9325ac935dc0837"
        "335a16e4ce17c1bb"
    )
)

# EX 协议帧头格式: head_flag(1B) + customize(4B) + version(1B) + zipsize(2B) + unzipsize(2B)
_EX_HEADER_FMT = "<BIBHH"


class MacExLoginCmd(BaseCommand[bool]):
    """MAC EX 扩展行情登录命令。"""

    def build_request(self) -> bytes:
        inner = struct.pack("<H", _MSG_ID) + _LOGIN_BODY
        header = struct.pack(
            _EX_HEADER_FMT,
            _HEAD_FLAG,
            0,  # customize
            1,  # version
            len(inner),
            len(inner),
        )
        return header + inner

    def parse_response(self, body: bytes) -> bool:
        # Login 响应 body 非空即视为成功
        return len(body) >= 2
