# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.2.0] - 2026-09-16

相对上游基线 `4820b4a` 的累积变更（首个独立发布版本）。

### Added

- **标准协议**：K 线便利方法 `get_bars` / `get_bars_range` / `get_k_data`；`get_history_transaction_all`（历史逐笔全量分页）；
  `get_security_features_all`；`get_trading_calendar` / `get_trading_days`；`get_formula`。
- **交易日历**（`easy_tdx.TradingCalendar`）：由指数日线构建，提供 `is_trading_day` / `prev_` / `next_trading_day` /
  `trading_days_between` / `count` / `recent` / `as_ints`。
- **MAC 协议**：`get_stock_quotes_list`（自定义字段 + 自动分页）、服务端复权 K 线、竞价、异动、chart sampling。
- **扩展市场**：`0x2422` 表格、`0x2455` 服务器信息、连接自动登录 `0x2454`、MAC 通道商品列表/报价/K线/逐笔。
- **F10 额外网关**：`AltF10Client`（`tdxhub.icfqs.com:7615`）——`share_capital_structure`（股本结构）、
  `valuation_history`（估值历史 PE/PB×1Y/3Y/5Y）、`hot_topic_overview`（题材信息面）、
  `balance_sheet`/`income_statement`/`cashflow_statement`（三表）、`business_composition`（主营构成）、
  `industry_rank`（行业排名）、`institutional_holding_detail`/`institutional_holding_price_compare`（机构持仓），均实测可用。
  另封装：`research_consensus`（研报一致预期）、`theme_boards`（题材板块族）、`company_events`（公司大事）、
  `company_basic`（公司基本资料）、`institutional_holding_dates`、`industry_chain`（产业链）、
  `industry_valuation`（行业估值对比）、`dragon_tiger_list`（龙虎榜）、`dividend_overview`/`dividend_viewer`（分红）、
  `industry_events`（行业重要事件）、`board_basic_info`（板块基础资料）、`northbound_funds`（北向持股）。
- **F10 / ICFQS（7615 TQLEX）**：公司概况/财报/题材/公告/北向/估值/涨跌停榜；龙虎榜/游资/每日复盘/题材（含异步）；**十大股东 / 机构持股 / 流通股东趋势 / 股东人数 / 股东人数排名**。
- **扩展命令**：`0x0452`(特殊涨跌停表)、`0x051a`(成交分布)、`0x051b`(分时副图)、`0x051c`(指数动量)、
  `0x051d`(指数概况)、`0x053f`(排行榜)、`0x0547`(加密行情)、`0x0fd1`(小走势图)。
- **离线**：`official` 官方历史数据下载（清单解析 + 断点续传 + 原子写）；`htc` 分笔容器读取（.htc 容器/标的帧 + zlib 块）。
- **通达信 zhb 配置扩展**：`get_ah_rates`（A/H 对照）、`get_adr_list`（ADR 对照）、`get_industry_chain`（产业链）、
  `get_named_blocks`（基金/美股/港股/中证/英股/新交所/三板板块成分）、`get_tdx_holidays`（内嵌节假日表 1991 至今）、
  `get_brokers`（券商名录）、`get_tdx_zs3`/`get_tdx_dszs`（板块/指数定义）、`get_sb_index_names`、
  `get_hk_index_weights`、`get_csrc_industries`（证监会行业）、`get_index_names`、`get_stock_pinyin`、
  `get_code_name_table`、`get_bj_code_map`（北交所新旧代码）、`get_hk_stock_concepts`/`get_us_stock_concepts`、
  `get_zhb_config`（通用 INI）、`get_stock_name_history`（**股票曾用名** profile.dat）、`get_bj_more`。
- **历史财务**：`read_history_financial_df` 快路径；point-in-time 面板（`report_date`）。
- **批量历史财务**：`download_financial_history(dir, start, end)`（季度 gpcw 断点续传 + 原子写）；
  `read_financial_history_panel(dir, codes)` 拼多季度 point-in-time 面板（每记录 ~584 字段）。
- **派生计算**：仿射复权因子与前后复权日线；基础日线（换手/市值等）；技术指标（MA/EMA/MACD/KDJ/BOLL/RSI/量比）。
- **公式解释器**（`easy_tdx.derive.formula`）：50+ 内置函数（REF/MA/EMA/SMA/SUM/HHV/LLV/STD/COUNT/CROSS/RSI/BARSLAST/
  BACKSET/SUMBARS/FILTER/HHVBARS/SLOPE/VAR/DMA/ZIG/PEAK/TROUGH/TR/ATR/OBV/PDI/MDI/ADX/ADXR/SAR 等）、
  运算符、变量赋值 `:`/`:=`、别名 IFF/AVERAGE/STDDEV。
- **工程**：限流（交易时段自适应）、连接池 `ParallelTdx`、批量下载器 `Downloader`、K 线语义校验、
  通用分页 helper `_paginate`、基金识别、CLI（`easy-tdx`）。
- **下载器增强**：`_coverage.json` 覆盖区间；`verify_coverage`（按交易日历查缺口）、`backfill_gaps`（补拉缺口）；
  同键合并**以新数据为准**（修正/复权更新生效）。
- **并发**：`ParallelTdx(mode="direct")` 每请求独立连接（参考 tdxrs：高并发下比连接池更稳）。
- **可配置重试**：`TdxClient(retry_delays=...)` / 环境变量 `EASY_TDX_RETRY_DELAYS` / config.json `retry_delays`。
- **服务器能力探测与选路**：`probe_capabilities`/`get_capabilities`（分项能力，缓存+持久化）；`from_best_host(require=[...])` 按能力选主机。
- **统一客户端容错**：`UnifiedTdxClient`/`AsyncUnifiedTdxClient` 对重叠方法（行情/逐笔）**MAC 优先、标准协议兜底**
  （`fallback_std=False` 可关闭）。
- **CLI**：`easy-tdx ping --caps` 附带能力列；新增 `easy-tdx caps` 命令（可 `--host`/`--limit`/`--refresh`）。

### Changed

- `AsyncTdxClient` 与 `TdxClient` **全面对齐**：补齐基金列表、复权因子/前后复权、基础日线、公式、股票汇总、
  财报批量下载等异步版（同步方法名一一对应）。
- 标准协议命令在旧版/纯报价服务器上**自动回退到全功能主机**（覆盖行情/逐笔/K 线）。
- 仿射复权对齐通达信服务端口径（`mul×raw+add`，误差 < 1e-4）。
- 离线解析向量化（numpy 结构化数组），显著提速。
- `mypy` strict 清零；全库 `ruff format`；lint/format 纳入 `examples/`。

### Fixed

- **版本号单一来源**：`easy_tdx.__version__` 此前仍为 `1.0.0`，与 `pyproject.toml`/CLI 的 `1.1.0` 不一致；
  现以 `src/easy_tdx/__init__.py` 为唯一源（hatch 动态版本），CLI 从包读取。
- **ICFQS 网关路由**：龙虎榜(`cfg_fx_yzlhb`)/每日复盘(`cfg_tk_mrfp`) 需走 `hot.icfqs.com`，此前全走默认网关导致
  HTTP 503；现按入口自动选网关。
- `config._save` 并发写竞争：`ParallelTdx` 多线程回退写配置时，固定 `config.tmp` 会被竞争移走导致 `FileNotFoundError`；
  改为进程/线程唯一临时名 + 进程内锁。
- F10/TQLEX 网关偶发返回空：`F10Client` 对空结果做有限重试（`empty_retries`），且空响应不入缓存。
- `ping_all` 单台主机失败不再中断整体优选。
- 修复 `get_security_list`(0x044d) 与 `get_sparkline`(0x0fd1) 同连接重复调用超时。
- 修复分时副图长度、多日分时解析、扩展登录残留帧等问题。

### Removed

- 移除 AI 工具相关文件：`.claude/`（含本地权限文件）、根目录 `CLAUDE.md`、及仅被其引用的 `scripts/ruff_hook.py`；
  `.claude/` 已加入 `.gitignore`。
- 清理误提交的下载产物与失效脚本；旧版 `api_reference.md` / `field_mapping.md` 合并进 `docs/数据字典.md`。

### Docs

- 新增 `docs/数据字典.md`（接口/命令/字段/口径）、`docs/能力矩阵.md`（成熟度与限制）、`docs/验证报告.md`、
  `docs/ROADMAP_补全方案.md`；README 增补快速上手与常见坑。

### CI / Tests

- CI：py3.10/3.12/3.13；`mypy`/`ruff` 阻断；覆盖率 `fail_under=50`。
- 单元测试覆盖协议编解码、离线解析、公式、CLI（mock）等；集成测试（`XMTDX_LIVE=1`）。
- 新增扩展行情命令离线单测（`tests/unit/test_ex_commands_offline.py`）与 MAC 命令/离线路径单测
  （`tests/unit/test_mac_commands_offline.py`）、CLI 连接工厂测试，覆盖率 ~64%。
- 全接口实测脚本 `scripts/verify_all.py`（逐项调用各通道公开 API，汇总 OK/EMPTY/FAIL；实测 **144/144 通过**）。

### Known limitations

- 免费协议不提供 Level-2（逐笔委托/十档/撤单）。
- `.htc` 分笔**记录级**解码未实现（无公开规范，参考实现亦未完成）；历史逐笔请用 `get_history_transaction_all`。
- `Market.BJ` 证券列表服务器端不稳定。
