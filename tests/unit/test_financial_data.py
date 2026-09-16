"""离线测试：专业财务数据解析。"""

import struct

from easy_tdx.codec.financial import parse_financial_dat, parse_financial_file_list
from easy_tdx.models.finance import FinancialFileInfo, FinancialRecord


class TestParseFinancialFileList:
    def test_basic(self) -> None:
        data = b"gpcw20260331.zip,abc123,5034901\ngpcw20251231.zip,def456,5737165\n"
        result = parse_financial_file_list(data)
        assert len(result) == 2
        assert result[0] == ("gpcw20260331.zip", "abc123", 5034901)
        assert result[1] == ("gpcw20251231.zip", "def456", 5737165)

    def test_empty(self) -> None:
        assert parse_financial_file_list(b"") == []

    def test_blank_lines_skipped(self) -> None:
        data = b"\ngpcw.zip,hash,100\n\n"
        result = parse_financial_file_list(data)
        assert len(result) == 1


class TestParseFinancialDat:
    def _build_dat(
        self,
        report_date: int = 20260331,
        stocks: list[tuple[str, int, list[float]]] | None = None,
    ) -> bytes:
        """构造一个最小的 .dat 二进制文件。"""
        if stocks is None:
            stocks = [("600519", 1, [1.0, 2.0, 3.0])]

        num_fields = len(stocks[0][2])
        report_size = num_fields * 4
        max_count = len(stocks)

        # Header: <1h I 1H 3L = 20 bytes
        header = struct.pack("<1hI1H3L", 0, report_date, max_count, 0, report_size, 0)

        index_fmt = "<6s1c1L"
        index_size = struct.calcsize(index_fmt)
        header_size = struct.calcsize("<1hI1H3L")
        data_start = header_size + max_count * index_size

        report_fmt = f"<{num_fields}f"

        # 先收集所有数据块，计算绝对偏移
        data_chunks: list[bytes] = []
        offset = data_start  # 绝对偏移
        offsets: list[int] = []
        for code, market_byte, fields in stocks:
            offsets.append(offset)
            chunk = struct.pack(report_fmt, *fields)
            data_chunks.append(chunk)
            offset += len(chunk)

        # 组装 index
        index_entries: list[bytes] = []
        for i, (code, market_byte, _) in enumerate(stocks):
            index_entries.append(
                struct.pack(index_fmt, code.encode("ascii"), bytes([market_byte]), offsets[i])
            )

        return header + b"".join(index_entries) + b"".join(data_chunks)

    def test_single_stock(self) -> None:
        dat = self._build_dat(stocks=[("600519", 1, [1.5, 2.5, 3.5])])
        result = parse_financial_dat(dat, report_date=20260331)
        assert len(result) == 1
        code, market, rdate, fields = result[0]
        assert code == "600519"
        assert market == b"\x01"  # SH
        assert rdate == 20260331
        assert len(fields) == 3
        assert abs(fields[0] - 1.5) < 1e-6

    def test_multiple_stocks(self) -> None:
        stocks = [
            ("000001", 0, [10.0, 20.0]),
            ("600036", 1, [30.0, 40.0]),
        ]
        dat = self._build_dat(stocks=stocks)
        result = parse_financial_dat(dat, report_date=20260630)
        assert len(result) == 2
        assert result[0][0] == "000001"
        assert result[0][1] == b"\x00"  # SZ
        assert result[1][0] == "600036"
        assert result[1][1] == b"\x01"  # SH

    def test_empty_data(self) -> None:
        assert parse_financial_dat(b"") == []
        assert parse_financial_dat(b"\x00" * 10) == []

    def test_report_date_from_header(self) -> None:
        dat = self._build_dat(report_date=20251231, stocks=[("000001", 0, [1.0])])
        result = parse_financial_dat(dat)  # report_date=0, should use header
        assert result[0][2] == 20251231


class TestFinancialModels:
    def test_file_info(self) -> None:
        fi = FinancialFileInfo(filename="gpcw.zip", hash="abc", filesize=100)
        assert fi.filename == "gpcw.zip"
        assert fi.filesize == 100

    def test_record(self) -> None:
        from easy_tdx.models.enums import Market

        r = FinancialRecord(
            code="600519", market=Market.SH, report_date=20260331, fields=[1.0, 2.0]
        )
        assert r.market == Market.SH
        assert len(r.fields) == 2
