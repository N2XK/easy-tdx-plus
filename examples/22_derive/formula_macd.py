"""演示：用通达信公式在个股 K 线上计算指标 / 选股信号。

`TdxClient.get_formula(market, code, formula, start_date, end_date)` 先按日期区间拉取
K 线，再用内置公式解释器（`easy_tdx.derive.formula.evaluate`）计算，返回各 `:` 输出列。

语法要点:
  - 输出 `NAME: expr;`（进入返回的 DataFrame），中间量 `NAME:= expr;`
  - 变量: OPEN/HIGH/LOW/CLOSE/VOL/AMOUNT（别名 O/H/L/C/V）
  - 运算符: + - * /、< > <= >= = <>、AND OR NOT
  - 函数: MA EMA SMA SUM HHV LLV STD REF CROSS COUNT RSI BARSLAST BARSLASTCOUNT
    HHVBARS LLVBARS BACKSET SUMBARS FILTER UPNDAY DOWNNDAY SLOPE VAR DMA ZIG
    PEAK TROUGH PEAKBARS TROUGHBARS SQRT POW LOG LN EXP SIGN MOD 等

下面公式等价于常用 MACD 指标，并给出 DIF 上穿 DEA 的金叉信号。
"""

from easy_tdx import KlineCategory, Market, TdxClient

MACD_FORMULA = """
DIF: EMA(CLOSE,12) - EMA(CLOSE,26);
DEA: EMA(DIF,9);
MACD: (DIF-DEA)*2;
GOLD: CROSS(DIF, DEA);
"""

with TdxClient.from_best_host() as c:
    df = c.get_formula(
        Market.SH,
        "600519",
        MACD_FORMULA,
        start_date=20250101,
        category=KlineCategory.DAY,
    )

print(f"贵州茅台 日线 MACD：{len(df)} 行")
print(f"金叉次数: {int(df['GOLD'].sum())}")
print()
print("最近 5 个交易日:")
print(df.tail(5).round(4).to_string())

# 运行结果（节选，随行情变化）:
# 贵州茅台 日线 MACD：415 行
# 金叉次数: 19
#
# 最近 5 个交易日:
#         DIF     DEA    MACD   GOLD
# 410 -0.6845  1.5050 -4.3791  False
# 411 -2.7690  0.6502 -6.8384  False
# 412 -4.1472 -0.3093 -7.6758  False
# 413 -5.5953 -1.3665 -8.4576  False
# 414 -7.7294 -2.6391 -10.1808 False
