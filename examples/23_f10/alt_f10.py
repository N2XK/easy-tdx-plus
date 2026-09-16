"""演示：tdxhub 网关的额外 F10 入口（AltF10Client）。

主网关 static.tdx.com.cn:7615 之外，tdxhub.icfqs.com:7615 提供额外入口
（TdxSharePCCW / TdxShareCW 命名空间），包括：
  - 股本结构变动历史（gbjg）
  - 估值历史序列（ph_agf10_gzfx，PE/PB/PS × 1Y/3Y/5Y）
  - 热点题材信息面概览（rdtc）

参数形态与主网关略有差异，AltF10Client 已按实测封装。
"""

from easy_tdx import AltF10Client

CODE = "600519"
c = AltF10Client(timeout=10)

# 股本结构
sc = c.share_capital_structure(CODE)
print("股本结构行数:", len(sc.rows))
for row in sc.rows[:3]:
    print("  ", row)

# 估值历史（近 1 年 PE）
val = c.valuation_history(CODE, period="1Y", indicator="PE")
print("\n估值历史行数:", len(val.rows), "| 末行:", val.rows[-1] if val.rows else None)

# 热点题材信息面概览
topics = c.hot_topic_overview(CODE)
print("\n题材概览行数:", len(topics.rows))
for row in topics.rows[:3]:
    print("  ", row.get("lmmc"), str(row.get("zynr"))[:40])

# 运行结果（节选，随行情变化）:
# 股本结构行数: 18
# 估值历史行数: 242 | 末行: {...}
# 题材概览行数: 24
