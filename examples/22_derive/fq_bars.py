"""演示：本地派生计算（复权 / 基础指标）。

  - get_fq_bars        基于 gbbq 除权除息本地计算前/后复权日线
  - get_adjust_factors 复权因子（hfq 最早=1，qfq 最新=1）
  - get_basic_daily    前收盘 / 涨跌幅 / 换手率 / 市值

使用客户端：TdxClient（同步）
"""

from easy_tdx import Market, TdxClient

with TdxClient.from_best_host() as c:
    # 前复权日线
    qfq = c.get_fq_bars(Market.SH, "600519", mode="qfq")
    print("前复权日线:", qfq.shape)
    print(qfq.tail(3).to_string(index=False))

    # 复权因子（仿射：mul×raw+add）
    fac = c.get_adjust_factors(Market.SH, "600519")
    print("\n复权因子:", fac.shape, "| 最新 qfq_mul =", fac["qfq_mul"].iloc[-1])

    # 基础指标（换手率 / 市值）
    basic = c.get_basic_daily(Market.SH, "600519")
    cols = ["date", "close", "pre_close", "change_pct", "turnover_pct", "float_mv"]
    print("\n基础指标:")
    print(basic[cols].tail(3).to_string(index=False))
