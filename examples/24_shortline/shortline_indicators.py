"""演示：短线指标（示例脚本，非库内置 API）。

在 easy_tdx 已有原始数据之上，组合出几个常用短线指标。这些指标包含
启发式口径，仅供参考，请按自己的交易体系调整：

  现价 / 涨跌幅      来自标准协议实时行情
  开盘涨幅           (开盘价 / 前收 - 1) × 100
  换手率             vol×100 / 流通股本（标准行情 vol 单位为手）
  封单比             买一量 / 流通股本（封单手数 → 股）
  竞价匹配量         集合竞价最后一点撮合量（MAC 集合竞价）
  主力净额           当日主力净流入（MAC 资金流向，单位：元）
  连板数             最近连续涨停天数（按板块涨停阈值判定）

使用客户端：TdxClient（行情/股本/K线）+ MacClient（竞价/资金流）
"""

from __future__ import annotations

import pandas as pd

from easy_tdx import MacClient, Market, TdxClient

CODES = [(Market.SH, "600519"), (Market.SZ, "000001")]


def _limit_pct(code: str) -> float:
    """按板块给出涨停幅度阈值（近似，用于判定连板）。"""
    if code.startswith(("30", "68")):
        return 19.8
    if code.startswith(("4", "8")):  # 北交所
        return 29.8
    return 9.8


def _limit_up_streak(bars: pd.DataFrame, code: str) -> int:
    """从日 K 线统计最近连续涨停天数。"""
    if bars.empty or len(bars) < 2:
        return 0
    closes = bars["close"].tolist()
    threshold = _limit_pct(code)
    streak = 0
    for i in range(len(closes) - 1, 0, -1):
        pct = (closes[i] / closes[i - 1] - 1) * 100
        if pct >= threshold:
            streak += 1
        else:
            break
    return streak


def main() -> None:
    rows: list[dict[str, object]] = []
    with TdxClient.from_best_host() as c, MacClient.from_best_host() as m:
        for market, code in CODES:
            quote = c.get_security_quotes([(market, code)])
            if quote.empty:
                print(f"{code}: 无行情（可能命中了不支持该命令的服务器）")
                continue
            q = quote.iloc[0]
            fin = c.get_finance_info(market, code)
            float_shares = float(fin.iloc[0]["liutong_guben"]) if not fin.empty else 0.0

            bars = c.get_bars_range(market, code, 20260601, 20991231)
            streak = _limit_up_streak(bars, code)

            auction = m.get_auction(market, code)
            auction_vol = int(auction["matched"].iloc[-1]) if not auction.empty else 0

            flow = m.get_capital_flow(market, code)
            main_net = float(flow.iloc[0]["main_net"]) if not flow.empty else 0.0

            price = float(q["price"])
            pre_close = float(q["pre_close"])
            vol_hand = float(q["vol"])
            bid1_hand = float(q["bid_vol1"])

            rows.append(
                {
                    "code": code,
                    "price": price,
                    "chg_pct": round((price / pre_close - 1) * 100, 2) if pre_close else None,
                    "open_chg_pct": round((float(q["open"]) / pre_close - 1) * 100, 2)
                    if pre_close
                    else None,
                    "turnover_pct": round(vol_hand * 100 / float_shares * 100, 3)
                    if float_shares
                    else None,
                    "seal_ratio": round(bid1_hand * 100 / float_shares * 100, 4)
                    if float_shares
                    else None,
                    "auction_vol": auction_vol,
                    "main_net_wan": round(main_net / 10000, 1),
                    "limit_up_streak": streak,
                }
            )

    df = pd.DataFrame(rows)
    print("短线指标快照：")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
