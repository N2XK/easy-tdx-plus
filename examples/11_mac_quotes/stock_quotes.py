"""演示：批量获取自定义字段报价。

通过 MacClient MAC 协议客户端（端口 7709）的 get_stock_quotes() 一次查询多只股票的
实时报价。stocks 参数为 [(Market, 代码), ...] 列表，默认返回 PresetField.COMMON 字段集，
单次最多查询 80 只。

参数:
    stocks  -- list[tuple[int, str]]，例如 [(Market.SH, "600519"), (Market.SZ, "000858")]
    fields  -- 字段选择，默认 None 即 PresetField.COMMON

返回 DataFrame 列说明:
    market      int     市场代码（0=深圳, 1=上海）
    code        str     证券代码
    name        str     证券名称
    price       float   最新价
    last_close  float   昨收价
    open        float   开盘价
    high        float   最高价
    low         float   最低价
    change      float   涨跌额（= price - last_close）
    change_pct  float   涨跌幅(%)
    volume      int     成交量（股）
    amount      float   成交额
"""

from easy_tdx import MacClient, Market

with MacClient.from_best_host() as c:
    # 批量查询多只股票报价（最多 80 只/次）
    df = c.get_stock_quotes(
        [
            (Market.SH, "600519"),  # 贵州茅台
            (Market.SZ, "000858"),  # 五粮液
        ]
    )
    print(df.to_string(index=False))

# 运行结果:
# market  code   name  price  last_close  open  high   low  change  change_pct  volume  amount
#      1  600519  贵州茅台 1521.00     1509.00  1510.00  1530.00  1505.00   12.00        0.80   15032  2285600000
#      0  000858  五粮液  132.50      131.20   131.50   133.80   130.80    1.30        0.99   42018   556800000
