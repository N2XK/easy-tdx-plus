"""演示：获取某历史日的**全部**逐笔成交（自动分页）。

`get_history_transaction_all()` 在 `get_history_transaction_data()` 之上自动翻页，
直到拉完当日全部逐笔，并按时间升序整理。实测服务器可回溯多年（示例为 2024-01-02）。

相比解析官方 g3tic/g4tic 的 `.htc`（单日全市场 ~80MB，记录级格式未公开），
按 (日期, 个股) 直接拉取更精准、更省资源，且能拿到成交量/方向等结构化字段。

DataFrame 列说明:
  datetime   Timestamp  成交时间（协议精度到分钟）
  price      float      成交价格（元）
  vol        int        成交量（股）
  num        int        成交笔数（该笔成交包含的撮合笔数）
  buyorsell  int        成交方向: 0=买, 1=卖, 2=中性, 8=集合竞价
"""

import pandas as pd

from easy_tdx import Market, TdxClient

with TdxClient.from_best_host() as c:
    date = 20240102
    df = c.get_history_transaction_all(Market.SZ, "000001", date)
    print(f"平安银行 {date} 全部逐笔: {len(df)} 笔")
    print(f"价格区间: {df['price'].min()} ~ {df['price'].max()}")
    print(f"总成交量: {df['vol'].sum():,} 股")
    print(f"时间范围: {df['datetime'].min()} ~ {df['datetime'].max()}")
    print()
    print("首/尾各 3 笔:")
    head_tail = pd.concat([df.head(3), df.tail(3)])
    print(head_tail[["datetime", "price", "vol", "buyorsell"]].to_string(index=False))

# 运行结果（节选）:
# 平安银行 20240102 全部逐笔: 4513 笔
# 价格区间: 9.21 ~ 9.42
# 总成交量: 1,158,366 股
# 时间范围: 2024-01-02 09:25:00 ~ 2024-01-02 15:00:00
#
# 首/尾各 3 笔:
#            datetime  price   vol  buyorsell
# 2024-01-02 09:25:00   9.39  6301          2
# 2024-01-02 09:30:00   9.40  1125          0
# 2024-01-02 09:30:00   9.38  5662          1
# 2024-01-02 14:56:00   9.22   152          0
# 2024-01-02 14:57:00   9.21    97          1
# 2024-01-02 15:00:00   9.21 19248          2
