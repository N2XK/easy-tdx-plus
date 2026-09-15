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
    with TdxClient.from_best_host(timeout=20.0) as c:
        df = c.get_stock_profile([(Market.SH, "600519")])
        assert len(df) == 1
        row = df.iloc[0]
        assert row["price"] > 0
        assert row["float_mv"] > 0
        assert 0 <= row["turnover_pct"] < 100


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
