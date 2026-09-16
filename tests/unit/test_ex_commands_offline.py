"""扩展行情（ex/commands）离线单测：用合成字节喂 parse_response。"""

from __future__ import annotations

import struct

import pytest

from easy_tdx.exceptions import TdxCommandError


def _pad(b: bytes, n: int) -> bytes:
    return b + b"\x00" * (n - len(b))


# --------------------------------------------------------------------------- #
# markets
# --------------------------------------------------------------------------- #


def test_ex_markets_parse() -> None:
    from easy_tdx.ex.commands.get_markets import GetExMarketsCmd

    skip = _pad(struct.pack("<B32sB2s", 0, b"skip", 0, b""), 64)  # cat=0&mkt=0 → 跳过
    rec = _pad(struct.pack("<B32sB2s", 31, "香港主板".encode("gbk"), 31, b"HK"), 64)
    body = struct.pack("<H", 2) + skip + rec
    out = GetExMarketsCmd().parse_response(body)
    assert len(out) == 1
    assert out[0].market == 31 and out[0].name == "香港主板" and out[0].short_name == "HK"


def test_ex_instrument_count_parse() -> None:
    from easy_tdx.ex.commands.get_instrument_count import GetExInstrumentCountCmd

    body = b"\x00" * 19 + struct.pack("<I", 123)
    assert GetExInstrumentCountCmd().parse_response(body) == 123
    assert GetExInstrumentCountCmd().parse_response(b"\x00") == 0


def test_ex_instrument_info_parse() -> None:
    from easy_tdx.ex.commands.get_instrument_info import GetExInstrumentInfoCmd

    rec = _pad(
        struct.pack("<BB3s9s17s9s", 1, 31, b"\x00\x00\x00", b"00700", b"Tencent", b"desc"),
        64,
    )
    body = struct.pack("<IH", 0, 1) + rec
    out = GetExInstrumentInfoCmd(start=0).parse_response(body)
    assert len(out) == 1
    assert out[0].code == "00700" and out[0].name == "Tencent" and out[0].desc == "desc"


# --------------------------------------------------------------------------- #
# quote
# --------------------------------------------------------------------------- #

_QUOTE_FMT = "<fffffIIIIIIIIIfffffIIIIIfffffIIIII"


def test_ex_instrument_quote_parse() -> None:
    from easy_tdx.ex.commands.get_instrument_quote import GetExInstrumentQuoteCmd

    fields = struct.pack(
        _QUOTE_FMT,
        9.5,
        9.6,
        9.9,
        9.4,
        9.9,  # pre_close/open/high/low/price
        0,
        0,
        100,
        50,
        0,
        10,
        20,
        0,
        30,  # kaicang..chicang
        1,
        2,
        3,
        4,
        5,
        11,
        12,
        13,
        14,
        15,
        6,
        7,
        8,
        9,
        10,
        21,
        22,
        23,
        24,
        25,
    )
    body = struct.pack("<B9s", 31, _pad(b"00700", 9)) + b"\x00\x00\x00\x00" + fields
    assert len(body) == 150
    q = GetExInstrumentQuoteCmd(31, "00700").parse_response(body)
    assert q is not None
    assert q.market == 31 and q.code == "00700"
    assert q.pre_close == pytest.approx(9.5) and q.price == pytest.approx(9.9)
    assert q.bid1 == pytest.approx(1.0) and q.ask_vol5 == 25
    assert GetExInstrumentQuoteCmd(31, "00700").parse_response(b"\x00") is None


def test_ex_instrument_quote_list_futures_and_error() -> None:
    from easy_tdx.ex.commands.get_instrument_quote_list import GetExInstrumentQuoteListCmd

    fields = struct.pack("<IfffffIIIIfIIfIfIIIIIIIIIfIIIIIIIII", *([0] * 35))
    rec = struct.pack("<B9s", 28, _pad(b"IF2401", 9)) + fields + b"\x00" * 150
    body = struct.pack("<H", 1) + rec
    out = GetExInstrumentQuoteListCmd(28, 3).parse_response(body)
    assert len(out) == 1 and out[0]["code"] == "IF2401" and out[0]["market"] == 28

    with pytest.raises(TdxCommandError):
        GetExInstrumentQuoteListCmd(28, 9).parse_response(body)


# --------------------------------------------------------------------------- #
# server info / table
# --------------------------------------------------------------------------- #


def test_ex_server_info_parse() -> None:
    from easy_tdx.ex.commands.get_server_info import GetExServerInfoCmd

    body = bytearray(260)
    struct.pack_into("<I", body, 0, 7)
    struct.pack_into("<I", body, 80, 20260916)
    struct.pack_into("<I", body, 84, 143015)
    body[16:41] = _pad("info-x".encode("gbk"), 25)
    body[41:70] = _pad("v1.0".encode("gbk"), 29)
    info = GetExServerInfoCmd().parse_response(bytes(body))
    assert info.delay == 7
    assert info.time_now == "2026-09-16 14:30:15"
    assert info.info == "info-x" and info.version == "v1.0"


def test_ex_table_parse() -> None:
    from easy_tdx.ex.commands.get_table import GetExTableCmd

    body = bytearray(169)
    struct.pack_into("<I", body, 35, 5)
    struct.pack_into("<I", body, 161, 2023)
    body += "表格内容".encode("gbk")
    chunk = GetExTableCmd(start=5).parse_response(bytes(body))
    assert chunk.start == 5 and chunk.count == 2023 and chunk.content == "表格内容"
    assert GetExTableCmd().parse_response(b"\x00").count == 0


# --------------------------------------------------------------------------- #
# transaction / minute
# --------------------------------------------------------------------------- #


def test_ex_transaction_parse() -> None:
    from easy_tdx.ex.commands.get_transaction import GetExTransactionDataCmd

    body = struct.pack("<B9s4sH", 28, _pad(b"IF2401", 9), b"\x00" * 4, 1)
    body += struct.pack("<HIIiH", 570, 9999, 100, 5, 20001)
    out = GetExTransactionDataCmd(28, "IF2401").parse_response(body)
    assert len(out) == 1
    r = out[0]
    assert (r.hour, r.minute, r.second) == (9, 30, 1)
    assert r.price == 9.999 and r.volume == 100 and r.zengcang == 5 and r.nature == 2


def test_ex_minute_time_parse() -> None:
    from easy_tdx.ex.commands.get_minute_time import GetExMinuteTimeDataCmd

    body = struct.pack("<B9sH", 31, _pad(b"00700", 9), 1)
    body += struct.pack("<HffII", 570, 1.5, 1.4, 100, 200)
    out = GetExMinuteTimeDataCmd(31, "00700").parse_response(body)
    assert len(out) == 1
    m = out[0]
    assert (m.hour, m.minute) == (9, 30)
    assert m.price == pytest.approx(1.5) and m.avg_price == pytest.approx(1.4) and m.volume == 100


def test_ex_bars_header_only() -> None:
    from easy_tdx.ex.commands.get_history_bars_range import GetExHistoryInstrumentBarsRangeCmd
    from easy_tdx.ex.commands.get_instrument_bars import GetExInstrumentBarsCmd

    assert GetExInstrumentBarsCmd(5, 31, "00700").parse_response(b"\x00" * 18 + b"\x00\x00") == []
    assert (
        GetExHistoryInstrumentBarsRangeCmd(31, "00700", 20240101, 20240201).parse_response(
            b"\x00" * 12 + b"\x00\x00"
        )
        == []
    )

    hist = GetExHistoryInstrumentBarsRangeCmd
    assert hist._parse_date(0)[0] == 2004
    assert hist._parse_time(570) == (9, 30)


# --------------------------------------------------------------------------- #
# login / setup / build_request
# --------------------------------------------------------------------------- #


def test_ex_login_and_setup() -> None:
    from easy_tdx.ex.commands.login import MacExLoginCmd
    from easy_tdx.ex.commands.setup import EX_SETUP_CMD

    cmd = MacExLoginCmd()
    req = cmd.build_request()
    assert len(req) == 10 + 2 + 80
    assert cmd.parse_response(b"\x00\x00") is True
    assert cmd.parse_response(b"\x00") is False
    assert isinstance(EX_SETUP_CMD, bytes) and len(EX_SETUP_CMD) > 0


def test_ex_build_requests_are_bytes() -> None:
    from easy_tdx.ex.commands.get_instrument_count import GetExInstrumentCountCmd
    from easy_tdx.ex.commands.get_instrument_info import GetExInstrumentInfoCmd
    from easy_tdx.ex.commands.get_markets import GetExMarketsCmd

    assert GetExMarketsCmd().build_request()
    assert GetExInstrumentCountCmd().build_request()
    assert len(GetExInstrumentInfoCmd(start=2000, count=50).build_request()) == 12 + 6


def test_instrument_bars_amount_is_seventh_field() -> None:
    """0x 扩展K线：amount 必须取记录第 7 个字段，不能是 position 的字节重解释。"""
    import struct

    from easy_tdx.ex.commands.get_instrument_bars import GetExInstrumentBarsCmd

    dt = struct.pack("<HH", (2026 - 2004) << 11 | 916, 14 * 60 + 15)
    rec = struct.pack("<ffffIIf", 10.0, 11.0, 9.5, 10.5, 8430, 515, 12.5)
    body = b"\x00" * 18 + struct.pack("<H", 1) + dt + rec
    bars = GetExInstrumentBarsCmd(3, 28, "AP2610").parse_response(body)
    assert len(bars) == 1
    b = bars[0]
    assert (b.open, b.high, b.low, b.close) == (10.0, 11.0, 9.5, 10.5)
    assert b.position == 8430 and b.trade == 515
    assert b.amount == 12.5  # 修复前是 1.18e-41（position 的浮点重解释）


def test_ex_transaction_price_scaled() -> None:
    """扩展逐笔价格必须 /1000（实测港股/美股/期货一致）。"""
    import struct

    from easy_tdx.ex.commands.get_transaction import GetExTransactionDataCmd

    # 头 16 字节 + 1 条 16 字节记录
    head = struct.pack("<B9s4sH", 31, b"00700", b"\x00" * 4, 1)
    rec = struct.pack("<HIIiH", 15 * 60 + 59, 433400, 200, 0, 0)
    body = head + rec
    items = GetExTransactionDataCmd(31, "00700").parse_response(body)
    assert len(items) == 1
    assert items[0].price == 433.4
    assert items[0].volume == 200
