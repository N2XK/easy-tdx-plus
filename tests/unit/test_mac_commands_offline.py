"""MAC 命令与离线路径工具离线单测（合成字节 / 临时目录）。"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# mac 服务器时段 (0x120F)
# --------------------------------------------------------------------------- #


def test_mac_server_info_parse() -> None:
    from easy_tdx.mac.commands.server_info import ServerInfoCmd

    body = bytearray(88)
    struct.pack_into("<H", body, 0, 3)
    struct.pack_into("<I", body, 22, 20260916)  # today
    struct.pack_into("<8H", body, 30, 570, 690, 780, 900, 0, 0, 0, 0)  # 9:30-11:30 / 13:00-15:00
    struct.pack_into("<8H", body, 46, 570, 690, 0, 0, 0, 0, 0, 0)
    body[62] = 1
    struct.pack_into("<I", body, 63, 20260915)  # last trading day
    struct.pack_into("<I", body, 71, 11)
    struct.pack_into("<I", body, 75, 22)

    s = ServerInfoCmd().parse_response(bytes(body))
    assert s.today == "2026-09-16" and s.last_trading_day == "2026-09-15"
    assert s.sessions_1[0] == {"open": "9:30", "close": "11:30"}
    assert s.market_param_1 == 11 and s.market_param_2 == 22

    short = ServerInfoCmd().parse_response(b"\x00" * 10)
    assert short.today == "" and short.last_trading_day == ""
    assert ServerInfoCmd().build_request()


# --------------------------------------------------------------------------- #
# mac K线偏移 (0x124A)
# --------------------------------------------------------------------------- #


def test_mac_kline_offset_parse() -> None:
    """0x124A 现按分类代码表解析：头部 8 字节 + N×35 字节记录。"""
    from easy_tdx.mac.commands.kline_offset import KlineOffsetCmd

    # 只有头部、未带记录 -> 空
    body = struct.pack(">I", 400000) + struct.pack("<I", 0)
    assert KlineOffsetCmd().parse_response(body) == []
    assert KlineOffsetCmd().parse_response(b"\x00") == []


# --------------------------------------------------------------------------- #
# mac 个股特征 (0x122A)
# --------------------------------------------------------------------------- #


def test_mac_symbol_info_parse() -> None:
    from easy_tdx.mac.commands.symbol_info import SymbolInfoCmd

    body = bytearray(194)
    struct.pack_into("<H22s44s", body, 8, 1, b"600519", "贵州茅台".encode("gbk"))
    struct.pack_into(
        "<III5ffIfII",
        body,
        96,
        20260916,  # date
        143015,  # time
        7,  # activity
        9.5,
        9.6,
        9.9,
        9.4,
        9.7,  # pre_close/open/high/low/close
        1.2,  # momentum
        12345,  # vol
        6789,  # amount
        100,  # inside
        200,  # outside
    )
    struct.pack_into("<HIf20xI3f", body, 148, 2, 0, 1.5, 5, 0.0, 3.3, 9.65)

    info = SymbolInfoCmd(1, "600519").parse_response(bytes(body))
    assert info.code == "600519" and info.name == "贵州茅台"
    assert info.time.strftime("%Y-%m-%d %H:%M:%S") == "2026-09-16 14:30:15"
    assert info.close == pytest.approx(9.7) and info.vol == 12345
    assert info.turnover == pytest.approx(3.3) and info.avg == pytest.approx(9.65)


# --------------------------------------------------------------------------- #
# mac 分时采样 (0x254D)
# --------------------------------------------------------------------------- #


def test_mac_chart_sampling_parse() -> None:
    from easy_tdx.mac.commands.chart_sampling import ChartSamplingCmd

    body = bytes(40) + struct.pack("<H", 2) + struct.pack("<f", 1.5) + struct.pack("<f", 1.6)
    prices = ChartSamplingCmd(31, "00700").parse_response(body)
    assert prices[0] == pytest.approx(1.5) and prices[1] == pytest.approx(1.6)
    assert ChartSamplingCmd(31, "00700").parse_response(b"\x00") == []


# --------------------------------------------------------------------------- #
# 离线路径定位
# --------------------------------------------------------------------------- #


def test_offline_finders(tmp_path: Path) -> None:
    from easy_tdx.offline.finders import find_5min_bar_file, find_lc1_bar_file, find_lc5_bar_file
    from easy_tdx.offline.paths import _market_to_exchange

    ex = _market_to_exchange(0)
    p5 = find_5min_bar_file(0, "000001", tmp_path)
    assert p5.name == f"{ex}000001.5" and p5.parent.name == "fzline"
    assert find_lc1_bar_file(0, "000001", tmp_path).name == f"{ex}000001.lc1"
    assert find_lc5_bar_file(0, "000001", tmp_path).name == f"{ex}000001.lc5"


# --------------------------------------------------------------------------- #
# 大文件分段拉取 (0x06B9)
# --------------------------------------------------------------------------- #


def test_report_file_cmd() -> None:
    from easy_tdx.commands.report_file import GetReportFileCmd

    req = GetReportFileCmd("gpcw.txt", start=0, length=30000).build_request()
    assert len(req) == 12 + 8 + 100
    assert GetReportFileCmd("x", 0).parse_response(b"\x00\x00\x00\x00abc") == b"abc"
    assert GetReportFileCmd("x", 0).parse_response(b"\x00") == b""


def test_mac_get_goods_list_delegates_to_mac_ex(monkeypatch) -> None:
    """MacClient.get_goods_list 必须走 MAC-EX，而不是 7709 上的 0x2562。"""
    import pandas as pd

    from easy_tdx.mac import client as mac_client
    from easy_tdx.mac.client import MacClient

    closed: list[bool] = []

    class _FakeMacEx:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def connect(self) -> None:
            pass

        def close(self) -> None:
            closed.append(True)

        def goods_list(self, market, start=0, count=600):
            self.calls.append((market, start, count))
            return pd.DataFrame({"market": [market], "code": ["00001"]})

    fake = _FakeMacEx()
    monkeypatch.setattr(
        "easy_tdx.ex.mac_client.MacExClient.from_best_host",
        classmethod(lambda cls, **kw: fake),
    )

    c = MacClient("127.0.0.1")
    df = c.get_goods_list(31, 0, 3)
    assert df.iloc[0]["market"] == 31
    assert fake.calls == [(31, 0, 3)]
    # 复用同一连接
    c.get_goods_list(74, 0, 3)
    assert fake.calls[-1] == (74, 0, 3)
    c.close()
    assert closed == [True]
    assert c._mac_ex is None
    assert mac_client  # 模块引用，避免未使用告警


def test_category_code_table_parse() -> None:
    """0x124A：解析分类代码表记录（实测 35 字节/条）。"""
    import struct

    from easy_tdx.mac.commands.kline_offset import KlineOffsetCmd

    recs = [
        b"\x00" + b"395001" + "主板Ａ股".encode("gbk") + b"\x00" * 8 + b"ZBAG" + b"\x00" * 8,
        b"\x00" + b"395002" + "主板Ｂ股".encode("gbk") + b"\x00" * 8 + b"ZBGB" + b"\x00" * 8,
        b"\x00" + b"395004" + "创业板".encode("gbk") + b"\x00" * 10 + b"CYB" + b"\x00" * 8,
    ]
    recs = [r[:35].ljust(35, b"\x00") for r in recs]
    body = struct.pack("<II", 0, len(recs)) + b"".join(recs)
    items = KlineOffsetCmd(0, 128000).parse_response(body)
    assert [(i.code, i.name, i.tag) for i in items] == [
        ("395001", "主板Ａ股", "ZBAG"),
        ("395002", "主板Ｂ股", "ZBGB"),
        ("395004", "创业板", "CYB"),
    ]


def test_category_code_table_small_count_returns_empty() -> None:
    import struct

    from easy_tdx.mac.commands.kline_offset import KlineOffsetCmd

    # 实测小 count 只回显头部、无记录
    body = struct.pack(">I", 5) + struct.pack("<I", 0)
    assert KlineOffsetCmd(0, 5).parse_response(body) == []


def test_file_download_failed_response_is_empty() -> None:
    """0x1217 失败回包（仅 8~9 字节头）不得返回垃圾字节。"""
    from easy_tdx.mac.commands.file_query import FileDownloadCmd

    assert FileDownloadCmd("zhb.zip").parse_response(b"\x00" * 8) == b""
    assert FileDownloadCmd("zhb.zip").parse_response(b"\x00" * 7) == b""
    assert FileDownloadCmd("zhb.zip").parse_response(b"\x00" * 8 + b"PK\x03\x04") == b"PK\x03\x04"


def test_download_file_raises_when_size_zero(monkeypatch) -> None:
    """MAC 文件接口不可用时，download_file 应显式报错而非静默返回空。"""
    import pytest

    from easy_tdx.exceptions import TdxCommandError
    from easy_tdx.mac.client import MacClient
    from easy_tdx.mac.commands.file_query import FileListCmd

    def fake_execute(self, cmd):  # noqa: ANN001
        if isinstance(cmd, FileListCmd):
            from easy_tdx.mac.commands.file_query import FileMeta

            return FileMeta(offset=0, size=0, flag=1, hash="")
        return b""

    monkeypatch.setattr(MacClient, "_execute", fake_execute)
    c = MacClient("127.0.0.1")
    with pytest.raises(TdxCommandError):
        c.download_file("zhb.zip")


def test_coerce_date_and_query_date_int() -> None:
    """query_date 接受 date/int/str，避免 int 触发 AttributeError。"""
    import struct
    from datetime import date

    from easy_tdx.codec.datetime_ import coerce_date
    from easy_tdx.mac.commands.symbol_transaction import SymbolTransactionCmd

    assert coerce_date(None) is None
    assert coerce_date(date(2026, 9, 16)) == date(2026, 9, 16)
    assert coerce_date(20260916) == date(2026, 9, 16)
    assert coerce_date("2026-09-16") == date(2026, 9, 16)

    for qd in (20260916, "20260916", date(2026, 9, 16)):
        req = SymbolTransactionCmd(1, "600519", query_date=qd).build_request()
        assert struct.pack("<I", 20260916) in req


def test_capital_flow_field_mapping() -> None:
    """0x1218：今日 4 值 + 5 日 6 值（口径同 gotdx）。"""
    import json
    import struct

    from easy_tdx.mac.commands.symbol_capital_flow import SymbolCapitalFlowCmd

    today = ["1209377792.00", "1379206784.00", "2098482304.00", "1928587136.00"]
    five = [
        "6430470144.00",
        "7608551424.00",
        "-626326144.00",
        "-307912640.00",
        "935576064.00",
        "-1486445.00",
    ]
    body = (
        struct.pack("<H12s5x8s", 1, b"Stock_ZJLX\x00\x00", b"") + json.dumps([today, five]).encode()
    )
    d = SymbolCapitalFlowCmd(1, "600519").parse_response(body)
    assert d is not None
    assert d.main_in == 1209377792.0 and d.main_out == 1379206784.0
    assert d.small_in == 2098482304.0 and d.small_net == d.small_in - d.small_out
    assert d.main_net_5d == 6430470144.0 - 7608551424.0
    assert d.super_large_net_5d == -626326144.0
    assert d.large_net_5d == -307912640.0
    assert d.medium_net_5d == 935576064.0
    assert d.small_net_5d == -1486445.0


def test_kline_offset_headers_and_records() -> None:
    """0x124A：Total 大端 / Returned 小端 + 35B 记录。"""
    import struct

    from easy_tdx.mac.commands.kline_offset import KlineOffsetCmd

    rec = (b"\x00" + b"395001" + "主板Ａ股".encode("gbk") + b"\x00" * 8 + b"ZBAG" + b"\x00" * 8)[
        :35
    ].ljust(35, b"\x00")
    body = struct.pack(">I", 7) + struct.pack("<I", 1) + rec
    cmd = KlineOffsetCmd(0, 128000)
    items = cmd.parse_response(body)
    assert cmd.total == 7 and cmd.returned == 1
    assert [(i.code, i.name, i.tag) for i in items] == [("395001", "主板Ａ股", "ZBAG")]

    # 只有头部（无记录）
    cmd2 = KlineOffsetCmd(0, 5)
    assert cmd2.parse_response(struct.pack(">I", 5) + struct.pack("<I", 0)) == []
    assert cmd2.total == 5 and cmd2.returned == 0
