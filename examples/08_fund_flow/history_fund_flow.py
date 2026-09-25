"""演示：获取个股历史日线资金流向序列。

使用 TdxClient 标准协议客户端，调用 get_history_fund_flow() 获取个股历史每日资金流向。
返回 HistoricalFundFlow DataFrame，每行代表一个交易日的资金流向数据。
优先走 Category 22 直连接口；若服务器返回空，自动回退为日K线+逐笔重算。

DataFrame 列说明:
  date         str              交易日期（datetime）
  super_in     float            超大单流入（元）
  super_out    float            超大单流出（元）
  large_in     float            大单流入（元）
  large_out    float            大单流出（元）
  medium_in    float            中单流入（元）
  medium_out   float            中单流出（元）
  small_in     float            小单流入（元）
  small_out    float            小单流出（元）

资金级别划分（按单笔成交金额）:
  超大单: > 100 万元
  大单:   20 ~ 100 万元
  中单:   4 ~ 20 万元
  小单:   <= 4 万元

数据特点:
  - start 为偏移量，0=最近交易日，count 为请求数量
  - 金额单位为元
  - 部分服务器不支持 Category 22，此时自动回退到逐笔重算模式（较慢）
"""

from easy_tdx import Market, TdxClient

with TdxClient.from_best_host() as c:
    df = c.get_history_fund_flow(Market.SH, "600519", 0, 10)
    print(f"贵州茅台 历史资金流向，共 {len(df)} 天:")
    print(df.to_string(index=False))

# 说明:
#   主路 0x052D 在公开免费服务器上普遍不可用，本示例实际走"日K + 逐笔重算"回退，
#   口径非官方、且逐日拉逐笔较慢。需要服务端真实口径请使用 MAC 协议的
#   MacClient.get_capital_flow（0x1218，今日 + 近5日；仅快照，无长历史）。
