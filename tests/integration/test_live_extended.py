"""扩展功能的真实服务器集成测试（默认跳过）。

运行：``XMTDX_LIVE=1 python -m pytest tests/integration/ -v``

覆盖：配置类加工数据（zhb）、本地复权、7615 F10、股票信息汇总，
以及多只股票的前复权 parity（本地 gbbq vs 服务端 MAC）。
"""

from __future__ import annotations

import os

import pytest

from easy_tdx import Adjust, F10Client, Market, Period, TdxClient

_LIVE_ENABLED = os.getenv("XMTDX_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason="set XMTDX_LIVE=1 to run live integration tests",
)

_PARITY_CODES = [
    (Market.SH, "600519"),
    (Market.SZ, "000001"),
    (Market.SH, "600036"),
    (Market.SZ, "000858"),
]


def test_live_zhb_config_data() -> None:
    with TdxClient.from_best_host(timeout=20.0) as c:
        files = c.get_zhb_files()
        assert len(files) > 20
        stat = c.get_tdx_stat()
        assert len(stat) > 1000
        assert {"code", "pe_ttm", "div_yield"} <= set(stat.columns)
        sp = c.get_spblock()
        assert any(b.name == "中证2000" for b in sp)
        hy = c.get_tdx_hy()
        assert len(hy) > 1000


def test_live_adjust_factors() -> None:
    with TdxClient.from_best_host(timeout=20.0) as c:
        fac = c.get_adjust_factors(Market.SH, "600519")
        assert len(fac) > 100
        last = fac.iloc[-1]
        first = fac.iloc[0]
        assert last["qfq_mul"] == pytest.approx(1.0) and last["qfq_add"] == pytest.approx(0.0)
        assert first["hfq_mul"] == pytest.approx(1.0) and first["hfq_add"] == pytest.approx(0.0)


def test_live_stock_profile() -> None:
    """股票信息汇总：字段齐全、结构与股本一致。

    注：`price`/`turnover_pct` 依赖**当日**行情，盘前或非交易日可能为 0，
    故此处只断言结构稳定项（不依赖盘中状态）。
    """
    with TdxClient.from_best_host(timeout=20.0) as c:
        df = c.get_stock_profile([(Market.SH, "600519")])
        assert len(df) == 1
        row = df.iloc[0]
        assert row["code"] == "600519"
        assert row["total_shares"] > 0 and row["float_shares"] > 0
        # 市值依赖当日价格，盘前可为 0；仅在非 0 时校验大小关系
        if row["float_mv"] > 0:
            assert row["total_mv"] >= row["float_mv"]


def test_live_f10() -> None:
    f10 = F10Client(timeout=10.0)
    profile = f10.company_profile("600519")
    assert profile.ok and profile.rows
    notices = f10.announcements("600519")
    assert len(notices.rows) > 0


def test_live_qfq_parity_multiple_stocks() -> None:
    """本地 gbbq 前复权应与服务端 MAC 前复权基本一致（多只股票）。"""
    from easy_tdx import MacClient

    with TdxClient.from_best_host(timeout=20.0) as c, MacClient.from_best_host() as m:
        for market, code in _PARITY_CODES:
            local = c.get_fq_bars(market, code, mode="qfq")
            local_map = dict(zip(local["date"].dt.strftime("%Y-%m-%d"), local["close"]))
            server = m.get_stock_kline(market, code, Period.DAILY, count=200, adjust=Adjust.QFQ)
            server_map = dict(zip(server["datetime"].dt.strftime("%Y-%m-%d"), server["close"]))
            common = sorted(set(local_map) & set(server_map))
            assert len(common) > 50, f"{code} 共同交易日过少"
            rel = [
                abs(local_map[d] - server_map[d]) / server_map[d] for d in common if server_map[d]
            ]
            mean_rel = sum(rel) / len(rel)
            assert mean_rel < 1e-4, f"{code} 复权偏差过大: mean_rel={mean_rel:.2e}"


def test_live_auction_series() -> None:
    """0x056a：集合竞价过程快照（当日 + 历史）。"""
    with TdxClient.from_best_host(timeout=5.0) as c:
        # 今日竞价：盘前/非交易日为空（正常），非空时校验字段
        today = c.get_auction_series(Market.SZ, "000001")
        assert set(today.columns) == {"time", "price", "matched", "unmatched"}
        if len(today):
            assert today["price"].iloc[0] > 0

        # 历史竞价：固定日期，会话无关
        hist = c.get_auction_series(Market.SZ, "000001", date=20260814)
        assert len(hist) > 0
        assert hist["price"].iloc[0] > 0
        assert hist["time"].iloc[0].hour == 9


def test_live_trading_status_and_suspended() -> None:
    """0x053e：交易状态字与停牌筛选；>80 只自动分批。"""
    from easy_tdx.models.quote import TRADING_STATUS_SUSPENDED

    with TdxClient.from_best_host(timeout=5.0) as c:
        listing = c.get_security_list(Market.SH, 0)
        codes = [(Market.SH, row["code"]) for _, row in listing.head(200).iterrows()]
        df = c.get_security_quotes(codes)  # 200 只 -> 自动分 3 批
        assert len(df) == len(codes)
        assert "trading_status" in df.columns

        susp = c.get_suspended_quotes(codes)
        assert (
            (susp["trading_status"].astype("int64") & TRADING_STATUS_SUSPENDED)
            .eq(TRADING_STATUS_SUSPENDED)
            .all()
        )


def test_live_mac_get_goods_list() -> None:
    """MacClient.get_goods_list 内部走 MAC-EX(7727)，应返回扩展市场商品。"""
    from easy_tdx import ExMarket
    from easy_tdx.mac.client import MacClient

    with MacClient.from_best_host(timeout=5.0) as c:
        df = c.get_goods_list(int(ExMarket.HK_MAIN_BOARD), 0, 3)
        assert len(df) == 3
        assert "name" in df.columns


def test_live_category_code_flags_match_connect_list() -> None:
    """0x124A flags bit24（互联互通）应与 MAC HK_CONNECT 名单一致。"""
    from easy_tdx.mac.client import MacClient
    from easy_tdx.mac.enums import Category, FilterType

    with MacClient.from_best_host(timeout=10) as c:
        connect = set(
            c.get_stock_quotes_list(Category.SZ, 0, 5000, exclude_flags=[FilterType.HK_CONNECT])[
                "code"
            ]
        )
        df = c.get_kline_offset()
    stocks = df[df["code"].str.startswith("000")]
    assert len(stocks) > 50
    match = (stocks["code"].isin(connect) == stocks["is_connect"]).all()
    assert match, "flags bit24 与互联互通名单不一致"


def test_live_ex_chart_sampling_session_aware() -> None:
    """0x254D（MAC-EX 专用）：美股必有数据；HK 在交易时段内应有数据。

    采样约每 4 分钟一点、上限 100；无当前时段数据时（盘前/未开盘）返回空，属正常。
    """
    from datetime import datetime
    from datetime import time as dtime
    from zoneinfo import ZoneInfo

    from easy_tdx import ExMarket
    from easy_tdx.ex.mac_client import MacExClient

    def hk_in_session() -> bool:
        now = datetime.now(ZoneInfo("Asia/Hong_Kong"))
        return now.weekday() < 5 and dtime(9, 30) <= now.time() <= dtime(16, 0)

    with MacExClient.from_best_host(timeout=10.0) as e:
        us = e.goods_chart_sampling(int(ExMarket.US_STOCK), "A")
        assert len(us) > 0
        assert all(p > 0 for p in us["price"])

        hk = e.goods_chart_sampling(int(ExMarket.HK_MAIN_BOARD), "00700")
        assert "price" in hk.columns
        if hk_in_session() and len(hk) == 0:
            pytest.fail("HK 交易时段内 0x254D 返回空（疑似服务器行为变化）")
