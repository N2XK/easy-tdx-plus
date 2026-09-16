"""F10（7615 TQLEX）数据能力普查。

遍历已封装的 F10 方法，调用单只股票并汇总每个入口的返回行数与字段清单，
用于评估"通达信 F10 还能补哪些基本面数据"。

用法::

    python scripts/f10_census.py --code 600519
    python scripts/f10_census.py --code 000001 --json > /tmp/f10.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from easy_tdx.f10 import F10Client


def _calls() -> list[tuple[str, str, Callable[[F10Client, str], object]]]:
    return [
        ("stock_info", "基础信息", lambda c, k: c.stock_info(k)),
        ("company_profile", "发行上市/公司概况", lambda c, k: c.company_profile(k)),
        ("business_periods", "主营构成报告期", lambda c, k: c.business_periods(k)),
        ("business_composition", "主营构成", lambda c, k: c.business_composition(k)),
        ("finance_report.zcfzb", "资产负债表", lambda c, k: c.finance_report(k, "zcfzb")),
        ("finance_report.lrb", "利润表", lambda c, k: c.finance_report(k, "lrb")),
        ("finance_report.xjllb", "现金流量表", lambda c, k: c.finance_report(k, "xjllb")),
        ("finance_diagnosis", "财务诊断", lambda c, k: c.finance_diagnosis(k)),
        ("stock_score", "个股总评", lambda c, k: c.stock_score(k)),
        ("profit_forecast", "盈利预测", lambda c, k: c.profit_forecast(k)),
        ("valuation", "估值(PE/PB/市值)", lambda c, k: c.valuation(k)),
        ("dividend_financing", "分红融资", lambda c, k: c.dividend_financing(k)),
        ("allotment_dates", "增发获配日期", lambda c, k: c.allotment_dates(k)),
        ("northbound_holding", "北向/主力持仓", lambda c, k: c.northbound_holding(k)),
        (
            "shareholder_change_plans",
            "股东增减持计划",
            lambda c, k: c.shareholder_change_plans(k),
        ),
        ("shareholder_report_dates", "股东报告期", lambda c, k: c.shareholder_report_dates(k)),
        ("top_shareholders", "十大股东", lambda c, k: c.top_shareholders(k, "20240930")),
        ("institutional_holding", "机构持股", lambda c, k: c.institutional_holding(k)),
        ("shareholder_count", "股东人数", lambda c, k: c.shareholder_count(k)),
        ("shareholder_count_rank", "股东人数排名", lambda c, k: c.shareholder_count_rank(k)),
        ("shareholder_trend", "流通股东趋势", lambda c, k: c.shareholder_trend(k)),
        ("annotation_governance", "治理", lambda c, k: c.governance(k)),
        ("ranking_detail", "排名", lambda c, k: c.ranking_detail(k)),
        ("hot_topics", "热点题材", lambda c, k: c.hot_topics(k)),
        ("theme_market", "题材概念行情", lambda c, k: c.theme_market(k)),
        ("topic_ids", "题材ID", lambda c, k: c.topic_ids(k)),
        ("company_news.gsyj", "公司研报", lambda c, k: c.company_news(k, "gsyj")),
        ("company_news.jgcs", "监管措施", lambda c, k: c.company_news(k, "jgcs")),
        ("announcements", "公告", lambda c, k: c.announcements(k)),
        ("news", "新闻", lambda c, k: c.news(k)),
        ("roadshows", "路演", lambda c, k: c.roadshows(k)),
    ]


def _columns(resp: object) -> list[str]:
    rows = getattr(resp, "rows", None)
    if not rows:
        return []
    cols: list[str] = []
    for row in rows:
        for key in row:
            if key not in cols:
                cols.append(key)
    return cols


def main() -> int:
    parser = argparse.ArgumentParser(description="F10 数据能力普查")
    parser.add_argument("--code", default="600519", help="股票代码（默认 600519）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    client = F10Client()
    report: list[dict[str, object]] = []
    for name, label, func in _calls():
        try:
            resp = func(client, args.code)
            rows = getattr(resp, "rows", []) or []
            report.append(
                {
                    "entry": name,
                    "label": label,
                    "status": "ok",
                    "rows": len(rows),
                    "columns": _columns(resp),
                }
            )
        except Exception as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            report.append({"entry": name, "label": label, "status": "error", "error": detail})

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"# F10 数据能力普查（样本 {args.code}）\n")
    print("| 入口 | 说明 | 状态 | 行数 | 字段 |")
    print("| --- | --- | --- | ---: | --- |")
    for item in report:
        if item["status"] == "ok":
            cols = ", ".join(item["columns"][:12])  # type: ignore[arg-type]
            print(f"| `{item['entry']}` | {item['label']} | ✅ | {item['rows']} | {cols} |")
        else:
            print(f"| `{item['entry']}` | {item['label']} | ❌ | - | {item['error']} |")
    ok = sum(1 for i in report if i["status"] == "ok")
    print(f"\n可用 {ok}/{len(report)} 个入口。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
