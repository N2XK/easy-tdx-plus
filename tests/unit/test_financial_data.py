"""离线测试：专业财务数据解析。"""

import io
import struct
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.codec.financial import parse_financial_dat, parse_financial_file_list
from easy_tdx.exceptions import TdxFileNotFoundError
from easy_tdx.models.finance import FinancialFileInfo, FinancialRecord
from easy_tdx.offline import read_history_financial, read_history_financial_df


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


class TestReadHistoryFinancialOffline:
    def _dat(self) -> bytes:
        return TestParseFinancialDat()._build_dat(
            stocks=[("000001", 0, [1.0, 2.0]), ("600036", 1, [3.0, 4.0])]
        )

    def test_read_dat(self, tmp_path: Path) -> None:
        path = tmp_path / "gpcw20260331.dat"
        path.write_bytes(self._dat())
        records = read_history_financial(path)
        assert len(records) == 2
        assert records[0].code == "000001"
        assert records[0].report_date == 20260331

    def test_read_df(self, tmp_path: Path) -> None:
        path = tmp_path / "gpcw20260331.dat"
        path.write_bytes(self._dat())
        df = read_history_financial_df(path)
        assert list(df.columns[:3]) == ["code", "market", "report_date"]
        assert float(df.iloc[0]["f0"]) == 1.0
        assert int(df.iloc[1]["market"]) == 1

    def test_read_zip(self, tmp_path: Path) -> None:
        path = tmp_path / "gpcw20260331.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("gpcw20260331.dat", self._dat())
        assert len(read_history_financial(path)) == 2

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(TdxFileNotFoundError):
            read_history_financial(tmp_path / "nope.dat")


def _gpcw_zip(path: Path, report_date: int, stocks: list[tuple[str, int, list[float]]]) -> None:
    dat = TestParseFinancialDat()._build_dat(report_date=report_date, stocks=stocks)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"gpcw{report_date}.dat", dat)


def test_read_financial_history_panel(tmp_path: Path) -> None:
    from easy_tdx.offline import read_financial_history_panel

    _gpcw_zip(tmp_path / "gpcw20240331.zip", 20240331, [("000001", 0, [1.0, 2.0])])
    _gpcw_zip(tmp_path / "gpcw20240630.zip", 20240630, [("000001", 0, [3.0, 4.0])])
    panel = read_financial_history_panel(tmp_path)
    assert panel["report_date"].tolist() == [20240331, 20240630]
    assert panel.iloc[0]["f0"] == 1.0 and panel.iloc[1]["f0"] == 3.0
    assert read_financial_history_panel(tmp_path, codes=["600000"]).empty


def test_download_financial_history(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from easy_tdx import TdxClient

    c = TdxClient(host="127.0.0.1")
    listing = pd.DataFrame(
        {
            "filename": [
                "tdxfin/gpcw20231231.zip",
                "tdxfin/gpcw20240331.zip",
                "tdxfin/gpcw20240630.zip",
            ]
        }
    )
    monkeypatch.setattr(c, "get_financial_file_list", lambda host=None: listing)
    calls: list[str] = []

    def fake_file(filename: str, host: str | None = None) -> bytes:
        calls.append(filename)
        buf = io.BytesIO()
        report = int(filename[-12:-4])
        dat = TestParseFinancialDat()._build_dat(report_date=report, stocks=[("000001", 0, [1.0])])
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("gpcw.dat", dat)
        return buf.getvalue()

    monkeypatch.setattr(c, "get_financial_file", fake_file)

    paths = c.download_financial_history(tmp_path, 20240101, 20241231)
    assert [p.name for p in paths] == ["gpcw20240331.zip", "gpcw20240630.zip"]
    assert calls == ["tdxfin/gpcw20240331.zip", "tdxfin/gpcw20240630.zip"]

    # 第二次应命中本地，不再下载
    calls.clear()
    c.download_financial_history(tmp_path, 20240101, 20241231)
    assert calls == []
