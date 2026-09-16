"""获取扩展行情成交数据（当日 + 历史）。

价格字段为整数，需除以 1000 才是真实价格（实测港股/美股/期货一致，
与同市场 quote/minute/bars 的口径对齐）。"""

import struct

from ...commands.base import BaseCommand
from ..models import ExTransactionRecord


class GetExTransactionDataCmd(BaseCommand[list[ExTransactionRecord]]):
    """获取当日分笔成交数据。"""

    def __init__(self, market: int, code: str, start: int = 0, count: int = 1800) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 08 00 03 01 12 00 12 00 fc 23")
        return header + struct.pack("<B9siH", self.market, self.code, self.start, self.count)

    def parse_response(self, body: bytes) -> list[ExTransactionRecord]:
        if len(body) < 16:
            return []
        pos = 0
        (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos : pos + 16])
        pos += 16
        return self._parse_records(body, pos, num)

    @staticmethod
    def _parse_records(body: bytes, pos: int, num: int) -> list[ExTransactionRecord]:
        results: list[ExTransactionRecord] = []
        for _ in range(num):
            if pos + 16 > len(body):
                break
            record_start = pos
            (raw_time, price, volume, zengcang, direction) = struct.unpack(
                "<HIIiH",
                body[pos : pos + 16],
            )
            pos += 16
            hour = raw_time // 60
            minute = raw_time % 60
            second = direction % 10000
            if second > 59:
                second = 0
            nature = direction // 10000
            results.append(
                ExTransactionRecord(
                    hour=hour,
                    minute=minute,
                    second=second,
                    price=price / 1000.0,
                    volume=volume,
                    zengcang=zengcang,
                    nature=nature,
                    _raw=body[record_start:pos],
                )
            )
        return results


class GetExHistoryTransactionDataCmd(BaseCommand[list[ExTransactionRecord]]):
    """获取历史某日分笔成交数据。"""

    def __init__(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> None:
        self.market = market
        self.code = code.encode("utf-8")
        self.date = date
        self.start = start
        self.count = count

    def build_request(self) -> bytes:
        header = bytes.fromhex("01 01 30 00 02 01 16 00 16 00 06 24")
        return header + struct.pack(
            "<IB9siH",
            self.date,
            self.market,
            self.code,
            self.start,
            self.count,
        )

    def parse_response(self, body: bytes) -> list[ExTransactionRecord]:
        if len(body) < 16:
            return []
        pos = 0
        (_market, _code, _unk, num) = struct.unpack("<B9s4sH", body[pos : pos + 16])
        pos += 16
        return GetExTransactionDataCmd._parse_records(body, pos, num)
