"""加密行情 0x0547 测试（离线）。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.commands.quotes_encrypt import GetQuotesEncryptCmd
from easy_tdx.models.enums import Market


def test_request_layout() -> None:
    req = GetQuotesEncryptCmd([(Market.SH, "600519"), (Market.SZ, "000001")]).build_request()
    assert req[10:12] == b"\x47\x05"  # cmd 0x0547
    payload = req[12:]
    assert struct.unpack_from("<H", payload, 0)[0] == 2
    # 每条 11 字节：market(1)+code(6)+0x56DA(2)+2(2)
    assert payload[2:4] == struct.pack("<B", 1) + b"6"
    assert payload[13:15] == struct.pack("<B", 0) + b"0"
    assert req[6:8] == struct.pack("<H", len(payload) + 2)


def test_too_many_codes() -> None:
    with pytest.raises(ValueError):
        GetQuotesEncryptCmd([(Market.SH, f"{i:06d}") for i in range(101)])


def test_parse_empty() -> None:
    # 响应逐字节 XOR 0x93；count=0 的两字节均为 0 -> 原字节 0x93
    body = bytes([0x93, 0x93])
    assert GetQuotesEncryptCmd([(Market.SH, "600519")]).parse_response(body) == []
