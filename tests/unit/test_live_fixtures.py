"""录制型 fixture 测试：把真实服务器响应（已解压 body）喂给解析器，锁住字段布局。

fixtures/mac_*.hex / ex_*.hex 为实盘录制；一旦解析器布局被误改（如
记录长度、字段偏移），这些断言会失败——用于防止"记录布局漂移"类严重 bug 回归。
"""

from __future__ import annotations

import pathlib

import pytest

FIX = pathlib.Path(__file__).parent.parent / "fixtures"


def load(name: str) -> bytes:
    return bytes.fromhex((FIX / f"{name}.hex").read_text().strip())


# --------------------------------------------------------------------------- #
# MAC
# --------------------------------------------------------------------------- #


def test_mac_server_info_fixture() -> None:
    from easy_tdx.mac.commands import ServerInfoCmd

    s = ServerInfoCmd().parse_response(load("mac_server_info"))
    assert s.today and s.last_trading_day
    assert s.sessions_1[0]["open"] == "9:30"


def test_mac_symbol_quotes_fixture() -> None:
    from easy_tdx.codec.bitmap import PresetField
    from easy_tdx.mac.commands import SymbolQuotesCmd

    items = SymbolQuotesCmd([(1, "600519")], PresetField.COMMON).parse_response(
        load("mac_symbol_quotes")
    )
    assert len(items) == 1
    q = items[0]
    assert (q.market, q.code, q.name) == (1, "600519", "贵州茅台")
    assert q.fields["pre_close"] == pytest.approx(1272.75, abs=0.01)
    assert q.fields["close"] == pytest.approx(1258.0, abs=0.01)
    assert q.fields["high"] >= q.fields["low"]


def test_mac_symbol_info_fixture() -> None:
    from easy_tdx.mac.commands import SymbolInfoCmd

    i = SymbolInfoCmd(1, "600519").parse_response(load("mac_symbol_info"))
    assert (i.code, i.name) == ("600519", "贵州茅台")
    assert i.pre_close == pytest.approx(1272.75, abs=0.01)
    assert i.high >= i.low and i.vol > 0


def test_mac_belong_board_fixture() -> None:
    from easy_tdx.mac.commands import SymbolBelongBoardCmd

    items = SymbolBelongBoardCmd(1, "600519").parse_response(load("mac_belong_board"))
    assert len(items) > 0
    assert all(b.board_code and b.board_name for b in items)


def test_mac_board_list_fixture() -> None:
    from easy_tdx.mac.commands import BoardListCmd

    items = BoardListCmd(start=0, page_size=5).parse_response(load("mac_board_list"))
    assert len(items) == 5
    assert all(b.code and b.name for b in items)


def test_mac_board_members_fixture() -> None:
    """板块成分（协议码 881001→21001）；字段位图 + 行布局错位会在此暴露。"""
    from easy_tdx.codec.bitmap import PresetField
    from easy_tdx.mac.client import _convert_board_code
    from easy_tdx.mac.commands import BoardMembersQuotesCmd

    code = _convert_board_code("881001")
    assert code == 21001
    items = BoardMembersQuotesCmd(
        code, start=0, page_size=20, fields=PresetField.COMMON
    ).parse_response(load("mac_board_members"))
    assert len(items) == 20
    assert all(len(m.code) == 6 and m.name for m in items)
    assert all("close" in m.fields for m in items)


def test_mac_unusual_fixture() -> None:
    from easy_tdx.mac.commands import UnusualCmd

    items = UnusualCmd(0, count=5).parse_response(load("mac_unusual"))
    assert len(items) == 5
    assert items[0].code and items[0].name and items[0].desc
    assert 0 <= items[0].time.hour <= 23


def test_mac_tick_charts_fixture() -> None:
    from easy_tdx.mac.commands import TickChartsCmd

    chart = TickChartsCmd(1, "600519", days=1).parse_response(load("mac_tick_charts"))
    assert chart.code == "600519"
    assert len(chart.charts) >= 1
    day = chart.charts[0]
    assert len(day.ticks) > 0
    assert day.ticks[0].price > 0


def test_mac_transaction_fixture() -> None:
    from easy_tdx.mac.commands import SymbolTransactionCmd

    items = SymbolTransactionCmd(1, "600519", None, 0, 3).parse_response(load("mac_transaction"))
    assert len(items) == 3
    assert all(t.price > 0 and t.vol >= 0 for t in items)


def test_mac_symbol_bar_fixture() -> None:
    from easy_tdx.mac.commands import SymbolBarCmd

    bars = SymbolBarCmd(1, "600519", count=3).parse_response(load("mac_symbol_bar"))
    assert len(bars) == 3
    for b in bars:
        assert b.high >= b.low and b.close > 0 and b.vol >= 0


def test_mac_file_query_dead_endpoint_fixture() -> None:
    """0x1215 在免费主站返回 size=0/flag=1（记录该事实，防止误当作可用）。"""
    from easy_tdx.mac.commands.file_query import FileListCmd

    meta = FileListCmd("zhb.zip").parse_response(load("mac_file_query"))
    assert meta.size == 0
    assert meta.flag == 1


# --------------------------------------------------------------------------- #
# EX（扩展行情 7727）
# --------------------------------------------------------------------------- #


def test_ex_markets_fixture() -> None:
    from easy_tdx.ex.commands.get_markets import GetExMarketsCmd

    markets = GetExMarketsCmd().parse_response(load("ex_markets"))
    assert len(markets) > 40
    assert all(m.market >= 0 for m in markets)


def test_ex_instrument_count_fixture() -> None:
    from easy_tdx.ex.commands.get_instrument_count import GetExInstrumentCountCmd

    assert GetExInstrumentCountCmd().parse_response(load("ex_instrument_count")) > 100_000


def test_ex_instrument_info_fixture() -> None:
    from easy_tdx.ex.commands.get_instrument_info import GetExInstrumentInfoCmd

    items = GetExInstrumentInfoCmd(start=0, count=3).parse_response(load("ex_instrument_info"))
    assert len(items) == 3
    assert all(i.code and i.name for i in items)


def test_ex_instrument_quote_fixture() -> None:
    from easy_tdx.ex.commands.get_instrument_quote import GetExInstrumentQuoteCmd

    q = GetExInstrumentQuoteCmd(31, "00700").parse_response(load("ex_instrument_quote"))
    assert q is not None
    assert q.code == "00700"
    assert q.price > 0 and q.pre_close > 0
    assert q.high >= q.low


def test_ex_instrument_quote_list_fixture() -> None:
    from easy_tdx.ex.commands.get_instrument_quote_list import GetExInstrumentQuoteListCmd

    rows = GetExInstrumentQuoteListCmd(31, 2, 0, 3).parse_response(load("ex_instrument_quote_list"))
    assert len(rows) == 3
    assert all(r["code"] and r["XianJia"] > 0 for r in rows)


def test_ex_instrument_bars_fixture() -> None:
    from easy_tdx.ex.commands.get_instrument_bars import GetExInstrumentBarsCmd

    bars = GetExInstrumentBarsCmd(2, 31, "00700", 0, 3).parse_response(load("ex_instrument_bars"))
    assert len(bars) == 3
    for b in bars:
        assert b.high >= b.low and b.close > 0
        assert (
            b.amount == pytest.approx(0.0) or b.amount > 0
        )  # 第7字段（旧实现会读成 position 的浮点重解释）


def test_ex_history_bars_range_fixture() -> None:
    from easy_tdx.ex.commands.get_history_bars_range import GetExHistoryInstrumentBarsRangeCmd

    bars = GetExHistoryInstrumentBarsRangeCmd(31, "00700", 20250101, 20250120).parse_response(
        load("ex_history_bars_range")
    )
    assert len(bars) > 0
    assert all(b.close > 0 for b in bars)


def test_ex_minute_time_fixture() -> None:
    from easy_tdx.ex.commands.get_minute_time import GetExMinuteTimeDataCmd

    bars = GetExMinuteTimeDataCmd(31, "00700").parse_response(load("ex_minute_time"))
    assert len(bars) > 0
    assert bars[0].price > 0 and bars[0].volume >= 0


def test_ex_transaction_price_scaled_fixture() -> None:
    """逐笔价格已 /1000（香港/美股/期货一致）；原始整数会被放大 1000 倍。"""
    from easy_tdx.ex.commands.get_transaction import GetExTransactionDataCmd

    items = GetExTransactionDataCmd(74, "A", 0, 3).parse_response(load("ex_transaction"))
    assert len(items) == 3
    assert all(0 < t.price < 10_000 for t in items)


def test_ex_server_info_fixture() -> None:
    from easy_tdx.ex.commands.get_server_info import GetExServerInfoCmd

    info = GetExServerInfoCmd().parse_response(load("ex_server_info"))
    assert "扩展" in info.version or info.version


def test_ex_instrument_quote_list_futures_fixture() -> None:
    """期货版 quote_list 使用另一套 140 字节布局（与港股版不同）。"""
    from easy_tdx.ex.commands.get_instrument_quote_list import GetExInstrumentQuoteListCmd

    rows = GetExInstrumentQuoteListCmd(28, 3, 0, 3).parse_response(
        load("ex_instrument_quote_list_futures")
    )
    assert len(rows) == 3
    # 非主力合约可能无成交（high/low=0），但昨结价与持仓量必有
    assert all(r["code"] and r["ZuoJie"] > 0 for r in rows)
    assert any(r["ChiCangLiang"] > 0 for r in rows)


def test_mac_capital_flow_fixture() -> None:
    """0x1218 真实 JSON：今日 4 值 + 5 日 6 值（field 口径同 gotdx）。"""
    from easy_tdx.mac.commands import SymbolCapitalFlowCmd

    d = SymbolCapitalFlowCmd(1, "600519").parse_response(load("mac_capital_flow"))
    assert d is not None
    assert d.main_in > 0 and d.main_out > 0
    assert d.main_net == pytest.approx(d.main_in - d.main_out)
    assert d.main_net_5d == pytest.approx(d.main_buy_5d - d.main_sell_5d)
    # 四类净额之和应接近 0（互补）
    total = d.super_large_net_5d + d.large_net_5d + d.medium_net_5d + d.small_net_5d
    scale = max(abs(d.super_large_net_5d), 1.0)
    assert abs(total) < 0.01 * scale


def test_ex_chart_sampling_fixture() -> None:
    """0x254D 缩略采样（MAC-EX/7727 专用）：42 字节头 + count×f32。

    A 股端口(7709)不响应此命令（代码内改用 0x122D）；HK/期货在无当前交易时段数据时
    返回空，故 fixture 用美股（有数据）。
    """
    from easy_tdx.mac.commands.chart_sampling import ChartSamplingCmd

    prices = ChartSamplingCmd(74, "A").parse_response(load("ex_chart_sampling"))
    assert len(prices) == 100
    assert all(p > 0 for p in prices)
