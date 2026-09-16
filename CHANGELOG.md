# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

自基线（原作者 `4820b4a`）以来的累积变更。

### Added

- **标准协议**：K 线便利方法 `get_bars` / `get_bars_range` / `get_k_data`；`get_history_transaction_all`（历史逐笔全量分页）；
  `get_security_features_all`；`get_trading_calendar` / `get_trading_days`；`get_formula`。
- **交易日历**（`easy_tdx.TradingCalendar`）：由指数日线构建，提供 `is_trading_day` / `prev_` / `next_trading_day` /
  `trading_days_between` / `count` / `recent` / `as_ints`。
- **MAC 协议**：`get_stock_quotes_list`（自定义字段 + 自动分页）、服务端复权 K 线、竞价、异动、chart sampling。
- **扩展市场**：`0x2422` 表格、`0x2455` 服务器信息、连接自动登录 `0x2454`、MAC 通道商品列表/报价/K线/逐笔。
- **F10 / ICFQS（7615 TQLEX）**：公司概况/财报/题材/公告/北向/估值/涨跌停榜；龙虎榜/游资/每日复盘/题材（含异步）。
- **扩展命令**：`0x0452`(特殊涨跌停表)、`0x051a`(成交分布)、`0x051b`(分时副图)、`0x051c`(指数动量)、
  `0x051d`(指数概况)、`0x053f`(排行榜)、`0x0547`(加密行情)、`0x0fd1`(小走势图)。
- **离线**：`official` 官方历史数据下载（清单解析 + 断点续传 + 原子写）；`htc` 分笔容器读取（.htc 容器/标的帧 + zlib 块）。
- **通达信 zhb 配置扩展**：`get_ah_rates`（A/H 对照）、`get_adr_list`（ADR 对照）、`get_industry_chain`（产业链）、
  `get_named_blocks`（基金/美股/港股/中证板块成分）、`get_tdx_holidays`（内嵌节假日表 1991 至今）。
- **历史财务**：`read_history_financial_df` 快路径；point-in-time 面板（`report_date`）。
- **派生计算**：仿射复权因子与前后复权日线；基础日线（换手/市值等）；技术指标（MA/EMA/MACD/KDJ/BOLL/RSI/量比）。
- **公式解释器**（`easy_tdx.derive.formula`）：50+ 内置函数（REF/MA/EMA/SMA/SUM/HHV/LLV/STD/COUNT/CROSS/RSI/BARSLAST/
  BACKSET/SUMBARS/FILTER/HHVBARS/SLOPE/VAR/DMA/ZIG/PEAK/TROUGH/TR/ATR/OBV/PDI/MDI/ADX/ADXR/SAR 等）、
  运算符、变量赋值 `:`/`:=`、别名 IFF/AVERAGE/STDDEV。
- **工程**：限流（交易时段自适应）、连接池 `ParallelTdx`、批量下载器 `Downloader`、K 线语义校验、
  通用分页 helper `_paginate`、基金识别、CLI（`easy-tdx`）。
- **可配置重试**：`TdxClient(retry_delays=...)` / 环境变量 `EASY_TDX_RETRY_DELAYS` / config.json `retry_delays`。

### Changed

- 标准协议命令在旧版/纯报价服务器上**自动回退到全功能主机**（覆盖行情/逐笔/K 线）。
- 仿射复权对齐通达信服务端口径（`mul×raw+add`，误差 < 1e-4）。
- 离线解析向量化（numpy 结构化数组），显著提速。
- `mypy` strict 清零；全库 `ruff format`；lint/format 纳入 `examples/`。

### Fixed

- `ping_all` 单台主机失败不再中断整体优选。
- 修复 `get_security_list`(0x044d) 与 `get_sparkline`(0x0fd1) 同连接重复调用超时。
- 修复分时副图长度、多日分时解析、扩展登录残留帧等问题。

### Removed

- 清理误提交的下载产物与失效脚本；旧版 `api_reference.md` / `field_mapping.md` 合并进 `docs/数据字典.md`。

### Docs

- 新增 `docs/数据字典.md`（接口/命令/字段/口径）、`docs/能力矩阵.md`（成熟度与限制）、`docs/验证报告.md`、
  `docs/ROADMAP_补全方案.md`；README 增补快速上手与常见坑。

### CI / Tests

- CI：py3.10/3.12/3.13；`mypy`/`ruff` 阻断；覆盖率 `fail_under=50`。
- 单元测试覆盖协议编解码、离线解析、公式、CLI（mock）等；集成测试（`XMTDX_LIVE=1`）。

### Known limitations

- 免费协议不提供 Level-2（逐笔委托/十档/撤单）。
- `.htc` 分笔**记录级**解码未实现（无公开规范，参考实现亦未完成）；历史逐笔请用 `get_history_transaction_all`。
- `Market.BJ` 证券列表服务器端不稳定。
