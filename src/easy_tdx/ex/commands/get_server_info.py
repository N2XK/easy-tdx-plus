"""扩展市场服务器信息命令（0x2455）。

无请求体；响应含延迟、版本、服务标识与服务器时间（固定偏移 GBK 字段）。
"""

from __future__ import annotations

from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import ExServerInfo

_MSG_ID = 0x2455


def _gbk(data: bytes) -> str:
    return data.decode("gbk", errors="replace").rstrip("\x00")


class GetExServerInfoCmd(BaseCommand[ExServerInfo]):
    """获取扩展市场服务器信息。"""

    def build_request(self) -> bytes:
        return build_mac_request(_MSG_ID, b"", head_flag=0x01)

    def parse_response(self, body: bytes) -> ExServerInfo:
        import struct

        delay = struct.unpack_from("<I", body, 0)[0] if len(body) >= 4 else 0
        date_now = struct.unpack_from("<I", body, 80)[0] if len(body) >= 84 else 0
        time_now = struct.unpack_from("<I", body, 84)[0] if len(body) >= 88 else 0
        year, month, day = date_now // 10000, (date_now % 10000) // 100, date_now % 100
        hour, minute, second = time_now // 10000, (time_now % 10000) // 100, time_now % 100
        time_text = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
        return ExServerInfo(
            delay=delay,
            info=_gbk(body[16:41]),
            version=_gbk(body[41:70]),
            server_sign=_gbk(body[117:130]),
            server_sign2=_gbk(body[240:253]),
            time_now=time_text,
            server_name=_gbk(body[159:189]),
            _raw=body,
        )
