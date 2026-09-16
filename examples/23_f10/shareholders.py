"""演示：通达信 F10 股东 / 机构数据（主网关，全部实测可用）。

覆盖 Tushare 的"股东/机构"强项：
  - 十大股东 / 十大流通股东趋势
  - 机构持股（汇总/趋势）
  - 股东人数（约 30 期）/ 股东人数排名
  - 股东增减持计划 / 北向持股

主网关：http://static.tdx.com.cn:7615/TQLEX（F10Client 默认）。
"""

from easy_tdx import F10Client

CODE = "600519"
f10 = F10Client(timeout=10)

# 十大股东（指定报告期）
top = f10.top_shareholders(CODE, "20240930")
print("十大股东:")
for row in top.rows[:5]:
    print(f"  {row.get('gd')}  持股 {row.get('cgs')}  占比 {row.get('bl')}%  {row.get('xz')}")

# 股东人数（约 30 期）
cnt = f10.shareholder_count(CODE)
print(f"\n股东人数: {len(cnt.rows)} 期")
if cnt.rows:
    r = cnt.rows[0]
    print(
        f"  {r.get('T002')} 股东 {r.get('T003')} 户 | 人均流通股 {r.get('T004')} | 较上期 {r.get('T005')}%"
    )

# 股东人数排名（跨个股）
rank = f10.shareholder_count_rank(CODE)
print("\n股东人数排名前 3:")
for row in rank.rows[:3]:
    print(f"  {row.get('zqjc')} {row.get('zqdm')}  股东 {row.get('T003')}  变化 {row.get('T005')}%")

# 机构持股
inst = f10.institutional_holding(CODE)
print(f"\n机构持股: {len(inst.rows)} 行")

# 十大流通股东趋势
trend = f10.shareholder_trend(CODE)
print(f"流通股东趋势: {len(trend.rows)} 行")

# 运行结果（节选，随行情变化）:
# 十大股东:
#   中国贵州茅台酒厂(集团)有限责任公司  持股 679211576  占比 54.07%  流通A股
#   香港中央结算有限公司  持股 86831284  占比 6.91%  流通A股
# ...
# 股东人数: 30 期
#   2026-06-30 股东 450712 户 | 人均流通股 43055.62 | 较上期 -1.51%
