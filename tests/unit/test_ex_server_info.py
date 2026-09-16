"""扩展市场服务器信息 0x2455 测试（离线）。"""

from __future__ import annotations

import struct

from easy_tdx.ex.commands.get_server_info import GetExServerInfoCmd


def _body() -> bytes:
    b = bytearray(327)
    struct.pack_into("<I", b, 0, 1274)  # delay
    b[16:41] = "测试扩展主站".encode("gbk").ljust(25, b"\x00")
    b[41:70] = "Win扩展 V1.0".encode("gbk").ljust(29, b"\x00")
    struct.pack_into("<I", b, 80, 20260916)  # date
    struct.pack_into("<I", b, 84, 92253)  # 09:22:53
    b[117:130] = b"SIGN1".ljust(13, b"\x00")
    b[159:189] = "延时全球_175".encode("gbk").ljust(30, b"\x00")
    b[240:253] = b"SIGN2".ljust(13, b"\x00")
    return bytes(b)


def test_ex_server_info_request_layout() -> None:
    req = GetExServerInfoCmd().build_request()
    assert req[10:12] == b"\x55\x24"  # msg id 0x2455
    assert req[0] == 0x01  # head flag (EX)


def test_ex_server_info_parse() -> None:
    info = GetExServerInfoCmd().parse_response(_body())
    assert info.delay == 1274
    assert info.info == "测试扩展主站"
    assert info.version == "Win扩展 V1.0"
    assert info.server_sign == "SIGN1"
    assert info.server_name == "延时全球_175"
    assert info.time_now == "2026-09-16 09:22:53"
