"""全接口实测：逐个调用各通道公开 API，汇总 通过 / 空 / 失败。

用法::

    python scripts/verify_all.py            # 全部
    python scripts/verify_all.py --group MAC
    python scripts/verify_all.py --json > report.json

需要联网。退出码：有 FAIL 时为 1。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

import pandas as pd

RESULTS: list[dict[str, object]] = []


def check(group: str, name: str, fn: Callable[[], object]) -> None:
    try:
        value = fn()
        if isinstance(value, (pd.DataFrame, pd.Series)):
            rows = int(len(value))
        elif isinstance(value, (list, tuple, dict, str, bytes)):
            rows = len(value)
        else:
            rows = 1 if value else 0
        RESULTS.append(
            {
                "group": group,
                "name": name,
                "status": "OK" if rows else "EMPTY",
                "rows": rows,
                "error": "",
            }
        )
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(
            {
                "group": group,
                "name": name,
                "status": "FAIL",
                "rows": 0,
                "error": f"{type(exc).__name__}: {exc}"[:140],
            }
        )


def _try_client(factory: Callable[[], object]) -> object | None:
    try:
        return factory()
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(
            {
                "group": "connect",
                "name": "from_best_host",
                "status": "FAIL",
                "rows": 0,
                "error": str(exc)[:140],
            }
        )
        return None


def run_standard() -> None:
    from easy_tdx import KlineCategory, Market, TdxClient

    c = _try_client(lambda: TdxClient.from_best_host(timeout=10))
    if c is None:
        return
    g = "标准"
    with c:
        check(g, "get_security_count", lambda: c.get_security_count(Market.SH))
        check(g, "get_security_list", lambda: c.get_security_list(Market.SH, 0))
        check(g, "get_security_list_all(1)", lambda: c.get_security_list_all(pages=1))
        check(g, "get_fund_list", lambda: c.get_fund_list(Market.SH, pages=1))
        check(
            g,
            "get_security_quotes",
            lambda: c.get_security_quotes([(Market.SH, "600519"), (Market.SZ, "000001")]),
        )
        check(g, "get_quotes_encrypt", lambda: c.get_quotes_encrypt([(Market.SH, "600519")]))
        check(
            g,
            "get_security_bars",
            lambda: c.get_security_bars(Market.SH, "600519", KlineCategory.DAY, 0, 10),
        )
        check(
            g,
            "get_index_bars",
            lambda: c.get_index_bars(Market.SH, "000001", KlineCategory.DAY, 0, 10),
        )
        check(g, "get_bars", lambda: c.get_bars(Market.SH, "600519", KlineCategory.DAY, 0, 10))
        check(
            g, "get_bars_range", lambda: c.get_bars_range(Market.SH, "600519", 20240101, 20240201)
        )
        check(g, "get_k_data", lambda: c.get_k_data("600519", 20240101, 20240201))
        check(g, "get_minute_time_data", lambda: c.get_minute_time_data(Market.SH, "600519"))
        check(
            g,
            "get_history_minute_time_data",
            lambda: c.get_history_minute_time_data(Market.SH, "600519", 20240102),
        )
        check(
            g, "get_minute_aux(buy_sell)", lambda: c.get_minute_aux(Market.SH, "600519", "buy_sell")
        )
        check(
            g,
            "get_minute_aux(volume_comparison)",
            lambda: c.get_minute_aux(Market.SH, "600519", "volume_comparison"),
        )
        check(g, "get_sparkline", lambda: c.get_sparkline(Market.SH, "600519"))
        check(g, "get_auction_series", lambda: c.get_auction_series(Market.SZ, "000001"))
        check(g, "get_transaction_data", lambda: c.get_transaction_data(Market.SH, "600519", 0, 50))
        check(
            g,
            "get_history_transaction_data",
            lambda: c.get_history_transaction_data(Market.SZ, "000001", 20240102, 0, 50),
        )
        check(
            g,
            "get_history_transaction_all",
            lambda: c.get_history_transaction_all(Market.SZ, "000001", 20240102),
        )
        check(g, "get_xdxr_info", lambda: c.get_xdxr_info(Market.SH, "600519"))
        check(g, "get_finance_info", lambda: c.get_finance_info(Market.SH, "600519"))
        check(
            g, "get_company_info_category", lambda: c.get_company_info_category(Market.SH, "600519")
        )
        check(g, "get_financial_file_list", lambda: c.get_financial_file_list())
        check(g, "get_fund_flow", lambda: c.get_fund_flow(Market.SH, "600519"))
        check(
            g, "get_history_fund_flow", lambda: c.get_history_fund_flow(Market.SH, "600519", 0, 30)
        )
        check(g, "get_market_stat", lambda: c.get_market_stat())
        check(g, "get_block_info", lambda: c.get_block_info("block_zs.dat"))
        check(g, "get_report_file", lambda: c.get_report_file("tdxhy.cfg"))
        check(
            g,
            "get_price_limits",
            lambda: c.get_price_limits(Market.SH, "600519", "贵州茅台", 1700.0),
        )
        check(g, "get_security_features", lambda: c.get_security_features(0, 2000))
        check(g, "get_security_features_all", lambda: c.get_security_features_all())
        check(g, "get_index_momentum", lambda: c.get_index_momentum(Market.SH, "000001"))
        check(g, "get_index_info", lambda: c.get_index_info(Market.SH, "000001"))
        check(g, "get_top_board", lambda: c.get_top_board())
        check(g, "get_volume_profile", lambda: c.get_volume_profile(Market.SH, "600519"))
        check(g, "get_stock_profile", lambda: c.get_stock_profile([(Market.SH, "600519")]))
        check(g, "get_zhb_files", lambda: c.get_zhb_files())
        check(g, "get_tdx_stat", lambda: c.get_tdx_stat())
        check(g, "get_tdx_stat2", lambda: c.get_tdx_stat2())
        check(g, "get_xgsg", lambda: c.get_xgsg())
        check(g, "get_spblock(False)", lambda: c.get_spblock(fill_index=False))
        check(g, "get_tdx_zs", lambda: c.get_tdx_zs())
        check(g, "get_tdx_bk", lambda: c.get_tdx_bk())
        check(g, "get_tdx_hy", lambda: c.get_tdx_hy())
        check(g, "get_ah_rates", lambda: c.get_ah_rates())
        check(g, "get_adr_list", lambda: c.get_adr_list())
        check(g, "get_industry_chain", lambda: c.get_industry_chain())
        check(g, "get_named_blocks", lambda: c.get_named_blocks("hkblock.dat"))
        check(g, "get_tdx_holidays", lambda: c.get_tdx_holidays())
        check(g, "get_brokers", lambda: c.get_brokers())
        check(g, "get_tdx_zs3", lambda: c.get_tdx_zs3())
        check(g, "get_tdx_dszs", lambda: c.get_tdx_dszs())
        check(g, "get_sb_index_names", lambda: c.get_sb_index_names())
        check(g, "get_hk_index_weights", lambda: c.get_hk_index_weights())
        check(g, "get_csrc_industries", lambda: c.get_csrc_industries())
        check(g, "get_index_names", lambda: c.get_index_names())
        check(g, "get_stock_pinyin", lambda: c.get_stock_pinyin())
        check(g, "get_code_name_table", lambda: c.get_code_name_table())
        check(g, "get_bj_code_map", lambda: c.get_bj_code_map())
        check(g, "get_bj_more", lambda: c.get_bj_more())
        check(g, "get_stock_name_history", lambda: c.get_stock_name_history())
        check(g, "get_zhb_config", lambda: c.get_zhb_config("hqrule.dat"))
        check(g, "get_trading_calendar", lambda: c.get_trading_calendar(20240101, 20240201))
        check(g, "get_trading_days", lambda: c.get_trading_days(20240101, 20240201))
        check(
            g,
            "get_formula",
            lambda: c.get_formula(Market.SH, "600519", "MA5: MA(CLOSE,5);", 20240101, 20240201),
        )
        check(g, "get_capabilities", lambda: c.get_capabilities())


def run_mac() -> None:
    from easy_tdx import Category, Market
    from easy_tdx.mac.client import MacClient

    c = _try_client(lambda: MacClient.from_best_host(timeout=10))
    if c is None:
        return
    g = "MAC"
    with c:
        check(g, "get_stock_quotes", lambda: c.get_stock_quotes([(Market.SH, "600519")]))
        check(g, "get_stock_quotes_list", lambda: c.get_stock_quotes_list(Category.A, count=20))
        check(g, "get_stock_kline", lambda: c.get_stock_kline(1, "600519", count=10))
        check(g, "get_tick_chart", lambda: c.get_tick_chart(1, "600519"))
        check(g, "get_tick_charts", lambda: c.get_tick_charts(1, "600519", days=5))
        check(g, "get_chart_sampling", lambda: c.get_chart_sampling(1, "600519"))
        check(g, "get_transactions", lambda: c.get_transactions(1, "600519", count=50))
        check(g, "get_symbol_info", lambda: c.get_symbol_info(1, "600519"))
        check(g, "get_board_list", lambda: c.get_board_list())
        check(g, "get_board_members", lambda: c.get_board_members("881001", count=20))
        check(g, "get_belong_board", lambda: c.get_belong_board(1, "600519"))
        check(g, "get_capital_flow", lambda: c.get_capital_flow(1, "600519"))
        check(g, "get_auction", lambda: c.get_auction(1, "600519"))
        check(g, "get_unusual", lambda: c.get_unusual(0, count=20))
        check(g, "get_goods_list", lambda: c.get_goods_list(31, 0, 3))
        check(g, "get_server_info", lambda: c.get_server_info())
        check(g, "get_kline_offset", lambda: c.get_kline_offset())


def run_ex() -> None:
    from easy_tdx import ExMarket
    from easy_tdx.ex.client import ExTdxClient
    from easy_tdx.ex.mac_client import MacExClient

    g = "扩展"
    c = _try_client(lambda: ExTdxClient.from_best_host(timeout=10))
    if c is not None:
        with c:
            check(g, "get_markets", lambda: c.get_markets())
            check(g, "get_instrument_count", lambda: c.get_instrument_count())
            check(g, "get_instrument_info", lambda: c.get_instrument_info(start=0, count=10))
            check(g, "get_server_info", lambda: c.get_server_info())
            check(g, "get_table", lambda: c.get_table(start=0))
    mac = _try_client(lambda: MacExClient.from_best_host(timeout=10))
    if mac is not None:
        mkt = int(ExMarket.HK_MAIN_BOARD)
        with mac:
            check(g, "mac goods_count", lambda: mac.goods_count(mkt))
            check(g, "mac goods_list", lambda: mac.goods_list(mkt, count=10))


def run_f10() -> None:
    from easy_tdx import AltF10Client, F10Client

    g = "F10"
    f = F10Client(timeout=10)
    code = "600519"
    check(g, "stock_info", lambda: f.stock_info(code))
    check(g, "company_profile", lambda: f.company_profile(code))
    check(g, "finance_report", lambda: f.finance_report(code))
    check(g, "finance_diagnosis", lambda: f.finance_diagnosis(code))
    check(g, "business_composition", lambda: f.business_composition(code))
    check(g, "dividend_financing", lambda: f.dividend_financing(code))
    check(g, "valuation", lambda: f.valuation(code))
    check(g, "profit_forecast", lambda: f.profit_forecast(code))
    check(g, "stock_score", lambda: f.stock_score(code))
    check(g, "hot_topics", lambda: f.hot_topics(code))
    check(g, "theme_market", lambda: f.theme_market(code))
    check(g, "northbound_holding", lambda: f.northbound_holding(code))
    check(g, "shareholder_change_plans", lambda: f.shareholder_change_plans(code))
    check(g, "top_shareholders", lambda: f.top_shareholders(code, "20240930"))
    check(g, "shareholder_count", lambda: f.shareholder_count(code))
    check(g, "shareholder_count_rank", lambda: f.shareholder_count_rank(code))
    check(g, "institutional_holding", lambda: f.institutional_holding(code))
    check(g, "shareholder_trend", lambda: f.shareholder_trend(code))
    check(g, "announcements", lambda: f.announcements(code))
    check(g, "news", lambda: f.news(code))
    check(g, "roadshows", lambda: f.roadshows(code))
    check(g, "company_news", lambda: f.company_news(code))
    check(g, "ranking_detail", lambda: f.ranking_detail(code))
    check(g, "governance", lambda: f.governance(code))

    ga = "AltF10"
    a = AltF10Client(timeout=10)
    check(ga, "share_capital_structure", lambda: a.share_capital_structure("000001"))
    check(ga, "valuation_history", lambda: a.valuation_history("600519"))
    check(ga, "hot_topic_overview", lambda: a.hot_topic_overview("600519"))
    check(ga, "balance_sheet", lambda: a.balance_sheet("600036"))
    check(ga, "income_statement", lambda: a.income_statement("600036"))
    check(ga, "cashflow_statement", lambda: a.cashflow_statement("600036"))
    check(ga, "business_composition", lambda: a.business_composition("600519", "20241231"))
    check(ga, "industry_rank", lambda: a.industry_rank("688318", "20250930"))
    check(
        ga,
        "institutional_holding_detail",
        lambda: a.institutional_holding_detail("000001", "20241231"),
    )
    check(
        ga,
        "institutional_holding_price_compare",
        lambda: a.institutional_holding_price_compare("000001"),
    )
    check(ga, "research_consensus", lambda: a.research_consensus("000001"))
    check(ga, "theme_boards", lambda: a.theme_boards("000001"))
    check(ga, "company_events", lambda: a.company_events("000001"))
    check(ga, "company_basic", lambda: a.company_basic("000001"))
    check(ga, "institutional_holding_dates", lambda: a.institutional_holding_dates("000001"))
    check(ga, "industry_chain", lambda: a.industry_chain(881426))
    check(ga, "industry_valuation", lambda: a.industry_valuation(881430, "301073"))
    check(ga, "dragon_tiger_list", lambda: a.dragon_tiger_list("000001", "20221129"))
    check(ga, "dividend_overview", lambda: a.dividend_overview("000001"))
    check(ga, "dividend_viewer", lambda: a.dividend_viewer("000001"))
    check(ga, "industry_events", lambda: a.industry_events(881430))
    check(ga, "board_basic_info", lambda: a.board_basic_info("001", "880976"))
    check(ga, "northbound_funds", lambda: a.northbound_funds("000001"))


def run_icfqs() -> None:
    from easy_tdx.f10 import IcfqsClient

    g = "ICFQS"
    c = IcfqsClient(timeout=10)
    check(g, "topics_hot", lambda: c.topics_hot())
    check(g, "daily_review_latest_date", lambda: c.daily_review_latest_date())
    check(g, "daily_review", lambda: c.daily_review("rq"))
    check(g, "lhb_detail", lambda: c.lhb_detail("600519", "20260101", "20260915"))
    check(
        g,
        "lhb_yyb_detail",
        lambda: c.lhb_yyb_detail("东方财富证券股份有限公司", "20260101", "20260915"),
    )
    check(g, "topic_rotation", lambda: c.topic_rotation())


def run_offline_derive() -> None:
    from easy_tdx import Market, TdxClient
    from easy_tdx.derive import add_indicators, evaluate

    g = "派生"
    c = _try_client(lambda: TdxClient.from_best_host(timeout=10))
    if c is None:
        return
    with c:
        bars = c.get_bars_range(Market.SH, "600519", 20240101, 20240601)
    check(g, "add_indicators", lambda: add_indicators(bars))
    check(g, "evaluate(MACD)", lambda: evaluate("D: EMA(CLOSE,12)-EMA(CLOSE,26);", bars))


def main() -> int:
    parser = argparse.ArgumentParser(description="全接口实测")
    parser.add_argument(
        "--group", default=None, help="仅跑某组（标准/MAC/扩展/F10/AltF10/ICFQS/派生）"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    groups: dict[str, Callable[[], None]] = {
        "标准": run_standard,
        "MAC": run_mac,
        "扩展": run_ex,
        "F10": run_f10,
        "ICFQS": run_icfqs,
        "派生": run_offline_derive,
    }
    for name, fn in groups.items():
        if args.group and args.group not in (name, "AltF10" if name == "F10" else name):
            continue
        fn()

    if args.json:
        print(json.dumps(RESULTS, ensure_ascii=False, indent=2))
    else:
        ok = sum(1 for r in RESULTS if r["status"] == "OK")
        empty = sum(1 for r in RESULTS if r["status"] == "EMPTY")
        fail = [r for r in RESULTS if r["status"] == "FAIL"]
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"FAIL  [{r['group']}] {r['name']}: {r['error']}")
        print(f"\n总计 {len(RESULTS)}：OK {ok} / EMPTY {empty} / FAIL {len(fail)}")
    return 1 if any(r["status"] == "FAIL" for r in RESULTS) else 0


if __name__ == "__main__":
    sys.exit(main())
