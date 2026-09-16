"""CLI 测试（离线，mock 连接工厂）。"""

from __future__ import annotations

from contextlib import contextmanager

import pandas as pd
import pytest
from click.testing import CliRunner

from easy_tdx.cli import cli, parsers
from easy_tdx.cli.output import format_output
from easy_tdx.mac.enums import Adjust, BoardType, Category, Period, SortOrder, SortType
from easy_tdx.models.enums import Market


class _FakeClient:
    """按方法名返回预设值，未定义的返回空 DataFrame。"""

    def __init__(self, **methods: object) -> None:
        self._methods = methods

    def __getattr__(self, name: str) -> object:
        return self._methods.get(name, lambda *a, **k: pd.DataFrame())


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    @contextmanager
    def cm():  # type: ignore[no-untyped-def]
        yield fake

    monkeypatch.setattr("easy_tdx.cli.conn.get_mac_client", cm)
    monkeypatch.setattr("easy_tdx.cli.conn.get_mac_ex_client", cm)


def _df() -> pd.DataFrame:
    return pd.DataFrame({"code": ["000001"], "price": [10.0], "name": ["平安银行"]})


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# --------------------------------------------------------------------------- #
# 基础 / 输出
# --------------------------------------------------------------------------- #


def test_version(runner: CliRunner) -> None:
    res = runner.invoke(cli, ["version"])
    assert res.exit_code == 0
    assert "1.1.0" in res.output


def test_root_help(runner: CliRunner) -> None:
    res = runner.invoke(cli, ["--help"])
    assert res.exit_code == 0
    for cmd in ("quote", "kline", "tick", "transaction", "ex"):
        assert cmd in res.output


def test_format_output_variants() -> None:
    df = _df()
    assert '"code"' in format_output(df, "json")
    assert "code" in format_output(df, "csv")
    assert "平安银行" in format_output(df, "table")
    assert format_output(pd.DataFrame(), "json") == "[]"
    assert format_output(pd.DataFrame(), "table") == ""
    with pytest.raises(Exception):
        format_output(df, "xml")


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #


def test_parse_market_period_adjust() -> None:
    assert parsers.parse_market("SZ") == Market.SZ
    assert parsers.parse_market("1") == Market.SH
    assert parsers.parse_market("2") == Market.BJ
    assert parsers.parse_period("DAILY") == Period.DAILY
    assert parsers.parse_period("5") == Period.MIN_5
    assert parsers.parse_adjust("QFQ") == Adjust.QFQ
    assert parsers.parse_adjust("2") == Adjust.HFQ


def test_parse_board_category_sort() -> None:
    assert parsers.parse_board_type("GN") == BoardType.GN
    assert parsers.parse_board_type("INDUSTRY") == BoardType.HY
    assert parsers.parse_category("KCB") == Category.KCB
    assert parsers.parse_sort_type("VOLUME") == SortType.VOLUME
    assert parsers.parse_sort_order("asc") == SortOrder.ASC


def test_parse_ex_market() -> None:
    assert parsers.parse_ex_market("HK") == parsers.parse_ex_market("HK_MAIN_BOARD")
    assert parsers.parse_ex_market("US") != parsers.parse_ex_market("HK")


def test_parse_stocks() -> None:
    out = parsers.parse_stocks("SZ 000001,SH 600000")
    assert [(int(m), c) for m, c in out] == [(int(Market.SZ), "000001"), (int(Market.SH), "600000")]


def test_parse_stocks_ambiguous_warns(runner: CliRunner) -> None:
    with runner.isolation():
        out = parsers.parse_stocks("000001")
    assert out == []


# --------------------------------------------------------------------------- #
# 命令（mock 客户端）
# --------------------------------------------------------------------------- #


def test_kline(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(get_stock_kline=lambda *a, **k: _df()))
    res = runner.invoke(cli, ["kline", "SZ", "000001", "--table", "--adjust", "QFQ"])
    assert res.exit_code == 0, res.output
    assert "000001" in res.output


def test_quote(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(get_stock_quotes=lambda *a, **k: _df()))
    res = runner.invoke(cli, ["quote", "SZ 000001"])
    assert res.exit_code == 0, res.output
    assert "000001" in res.output


def test_quote_list(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(get_stock_quotes_list=lambda *a, **k: _df()))
    res = runner.invoke(cli, ["quote-list", "A", "--count", "5"])
    assert res.exit_code == 0, res.output


@pytest.mark.parametrize(
    ("args", "method"),
    [
        (["board-list"], "get_board_list"),
        (["board-members", "881001"], "get_board_members"),
        (["belong-board", "SZ", "000001"], "get_belong_board"),
        (["capital-flow", "SZ", "000001"], "get_capital_flow"),
        (["auction", "SZ", "000001"], "get_auction"),
        (["unusual", "SZ"], "get_unusual"),
        (["server-info"], "get_server_info"),
        (["symbol-info", "SZ", "000001"], "get_symbol_info"),
        (["tick", "SZ", "000001"], "get_tick_chart"),
        (["transaction", "SZ", "000001"], "get_transactions"),
    ],
)
def test_simple_commands(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, args: list[str], method: str
) -> None:
    _patch(monkeypatch, _FakeClient(**{method: lambda *a, **k: _df()}))
    res = runner.invoke(cli, args)
    assert res.exit_code == 0, res.output


def test_market_stat(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    class _Ctx:
        def __enter__(self) -> object:
            return self

        def __exit__(self, *a: object) -> bool:
            return False

        def get_market_stat(self) -> pd.DataFrame:
            return _df()

    monkeypatch.setattr(
        "easy_tdx.client.TdxClient.from_best_host",
        classmethod(lambda cls, *a, **k: _Ctx()),
    )
    res = runner.invoke(cli, ["market-stat"])
    assert res.exit_code == 0, res.output


def test_ex_kline_and_quote(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(
        monkeypatch,
        _FakeClient(goods_kline=lambda *a, **k: _df(), goods_quotes=lambda *a, **k: _df()),
    )
    assert runner.invoke(cli, ["ex", "kline", "HK_MAIN_BOARD", "00700"]).exit_code == 0
    assert runner.invoke(cli, ["ex", "quote", "HK_MAIN_BOARD", "00700"]).exit_code == 0


def test_ping(runner: CliRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("easy_tdx.transport.sync.ping_all", lambda *a, **k: [("1.1.1.1", 0.012)])
    monkeypatch.setattr("easy_tdx.transport.sync.ping_mac_all", lambda *a, **k: [("2.2.2.2", 0.02)])
    res = runner.invoke(cli, ["ping", "--table"])
    assert res.exit_code == 0, res.output
    assert "1.1.1.1" in res.output


# --------------------------------------------------------------------------- #
# 未实现子命令（应显式报错，而非静默）
# --------------------------------------------------------------------------- #


def test_f10_stub_errors(runner: CliRunner) -> None:
    res = runner.invoke(cli, ["f10", "SZ", "000001"])
    assert res.exit_code != 0


def test_fund_flow_stub_errors(runner: CliRunner) -> None:
    res = runner.invoke(cli, ["fund-flow", "SZ", "000001"])
    assert res.exit_code != 0
