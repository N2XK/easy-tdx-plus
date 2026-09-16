"""演示：批量下载季度历史财务（gpcw）并构造按报告期的财务面板（回测需自行按公告滞后）。

- `TdxClient.download_financial_history(dir, start, end)`：从计算服务器按报告期区间
  批量下载 `gpcwYYYYMMDD.zip`（断点续传 + 原子写）。
- `read_financial_history_panel(dir, codes)`：把多季度文件拼成按报告期的财务面板
  （`code / market / report_date / f0..fN`，每记录约 584 个字段）。

用途：回测时按"报告期"取财务，避免前视偏差；服务器保留 1988 至今约 147 个季度。
"""

from pathlib import Path

from easy_tdx import TdxClient
from easy_tdx.offline import read_financial_history_panel

DATA_DIR = Path("gpcw_data")

with TdxClient.from_best_host() as c:
    # 1) 查看可用季度（148 个左右）
    listing = c.get_financial_file_list()
    print("可用财报季度数:", len(listing))
    print("最新:", listing["filename"].iloc[0], "| 最早:", listing["filename"].iloc[-1])

    # 2) 批量下载最近两年（已存在则跳过）
    paths = c.download_financial_history(DATA_DIR, 20230101, 20241231)
    print("本地季度文件:", [p.name for p in paths])

# 3) 构造某只股票按报告期的财务面板（回测需自行按公告滞后）
panel = read_financial_history_panel(DATA_DIR, codes=["000001"])
print("\n000001 面板行数:", len(panel), "报告期:", sorted(panel["report_date"].unique()))
print(panel[["code", "market", "report_date"]].to_string(index=False))

# 运行结果（节选，随服务器更新）:
# 可用财报季度数: 147
# 最新: gpcw20260930.zip | 最早: gpcw19881231.zip
# 本地季度文件: ['gpcw20230331.zip', 'gpcw20230630.zip', ...]
# 000001 面板行数: 8 报告期: [20230331, 20230630, 20230930, 20231231, ...]
