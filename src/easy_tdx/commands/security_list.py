"""获取证券列表命令（每页最多1000条，按 start 分页）。

修复 pytdx Bug #2：GBK 解码使用 errors='replace'，截断多字节序列不再崩溃。
修复 pytdx Bug #3：pre_close 保持使用通达信自定义浮点解码。
"""

import struct

from .._binary import slice_bytes, unpack_from
from ..codec.volume import _decode_volume
from ..models.enums import Market
from ..models.security import SecurityInfo
from .base import BaseCommand

_RECORD_SIZE = 29


class GetSecurityListCmd(BaseCommand[list[SecurityInfo]]):
    """获取指定市场从 start 开始的证券列表。"""

    def __init__(self, market: Market, start: int, count: int = 1000) -> None:
        self.market = market
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        # header(12) + payload: market(u16) + start(u32) + count(u32) + zero(u32) = 14
        # 注意：长度字段 = payload + 2（用旧版 0x0450 短包会致同连接重复调用失步）
        payload = struct.pack("<HIII", int(self.market), self.start, self.count, 0)
        pkg_len = len(payload) + 2
        header = struct.pack("<HIHH", 0x010C, 0x01010008, pkg_len, pkg_len)
        return header + struct.pack("<H", 0x044D) + payload

    def parse_response(self, body: bytes) -> list[SecurityInfo]:
        (num,) = unpack_from("<H", body, 0, "security_list header")
        pos = 2
        results: list[SecurityInfo] = []

        for _ in range(num):
            raw = slice_bytes(body, pos, _RECORD_SIZE, "security_list record")
            (
                code_bytes,
                volunit,
                name_bytes,
                _unknown1,  # 4字节，含义未明
                decimal_point,
                pre_close_raw,
                _unknown2,  # 4字节，含义未明
            ) = struct.unpack("<6sH8s4sBI4s", raw)

            code = code_bytes.decode("utf-8", errors="replace").rstrip("\x00")
            # Bug #2 修复：errors='replace' 避免截断 GBK 多字节序列时崩溃
            name = name_bytes.decode("gbk", errors="replace").rstrip("\x00")

            # pre_close_raw 与协议里的成交量/股本字段一样，使用通达信自定义浮点编码。
            pre_close = _decode_volume(pre_close_raw)

            results.append(
                SecurityInfo(
                    market=self.market,
                    code=code,
                    name=name,
                    volunit=volunit,
                    decimal_point=decimal_point,
                    pre_close=pre_close,
                    _raw=raw,
                )
            )
            pos += _RECORD_SIZE

        return results
