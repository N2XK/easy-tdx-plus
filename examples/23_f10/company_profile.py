"""演示：7615 F10 资料数据（HTTP 网关）。

7615 是通达信 F10 的 HTTP 网关（区别于 7709 行情）。
  - 公司概况 / 财务报表 / 主营构成 / 分红融资
  - 估值 / 热点题材 / 公告 / 北向持股 / 涨跌停榜

使用客户端：F10Client（同步）/ AsyncF10Client（异步）
"""

import asyncio

from easy_tdx import AsyncF10Client, F10Client

CODE = "600519"

f10 = F10Client(timeout=10)
# 公司概况（发行上市信息）
print("公司概况:", f10.company_profile(CODE).first_row())

# 财务报表（资产负债表，多期）
report = f10.finance_report(CODE)
print("\n财报期数:", len(report.rows), "| 最新期:", report.first_row().get("rq"))

# 热点题材
topics = f10.hot_topics(CODE)
print("\n热点题材:")
for row in topics.rows[:3]:
    print("  ", row.get("ztmc"), row.get("rxsj"), str(row.get("ztnr"))[:30])

# 公告
notices = f10.announcements(CODE)
print("\n公告数:", len(notices.rows), "| 最新:", notices.first_row().get("title"))

# 估值
valuation = f10.valuation(CODE)
print("\n估值表行数:", len(valuation.rows))


# 异步版本
async def main() -> None:
    af10 = AsyncF10Client(timeout=10)
    resp = await af10.company_profile(CODE)
    print("\n[async] 公司概况 T035 =", resp.first_row().get("T035"))


asyncio.run(main())
