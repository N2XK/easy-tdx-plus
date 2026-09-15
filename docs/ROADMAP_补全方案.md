# easy_tdx 补全方案（Roadmap）

> 目标：在 `easy_tdx` 之上补齐通达信 **免费 L1** 范围内的"加工数据"，
> 覆盖 `injoyai/tdx`、`eltdx`、`tdx2db` 等项目的增量能力。
>
> 不在范围内：Level-2（逐笔委托 / 十档盘口 / 撤单）、完整历史 tick / 历史分时
> （这些需付费数据源，公共服务器不提供）。

## 背景（为什么以此为主干）

| 项目 | 语言 | 许可 | 独有能力 | 缺口 |
| --- | --- | --- | --- | --- |
| **easy_tdx**（主干） | Python | MIT | MAC 协议、港/美/期货扩展市场、离线读取 | 7615 F10、配置类统计 |
| eltdx | Python(+Rust) | Research-Only | **7615 F10**（财报/题材/公告/北向…） | 扩展市场 |
| injoyai/tdx | Go | MIT | tdxstat / xgsg / 申万行业 / spblock / ExHq | 7615 F10 |
| tdx2db | Go | MIT | 复权因子 / 换手率 / 市值 / 落库视图 | 取数广度 |

选择 `easy_tdx` 作主干：MIT 可商用、纯 Python 易扩展、已具备扩展市场与离线能力。
缺口从同为 MIT 的 `injoyai/tdx`、`tdx2db` 移植，7615 F10 依据公开协议独立实现。

## 关键事实

- **zhb.zip**：通过标准协议 `0x06B9`（`get_report_file("zhb.zip")`）下载，内含 46 个
  配置文件，含 `tdxstat.cfg` / `tdxstat2.cfg` / `xgsg.cfg` / `spblock.dat` /
  `tdxzs.cfg` / `tdxbk.cfg`（`tdxhy.cfg` 走单独的 report file）。
- **7615 F10**：是 **HTTP 网关**（非二进制协议）：
  `POST http://static.tdx.com.cn:7615/TQLEX?Entry=<entry>`，
  body `{"Params":[...]}` 或自定义 JSON，响应 `{ResultSets:[...], ErrorCode}`。
  另一网关 `http://hot.icfqs.com:7615/TQLEX`（涨跌停榜）。

## 阶段与里程碑

### M1 · T1 配置类加工数据（低风险）
- 新增 `codec/configdata.py`：纯解析器
  `parse_tdxstat` / `parse_tdxstat2` / `parse_xgsg` / `parse_spblock` /
  `parse_tdxzs` / `parse_tdxbk` / `parse_tdxhy` / `unzip_zhb`
- 新增 `models/configdata.py`：`TdxStat` / `TdxStat2` / `TdxXgsg` /
  `SpBlock` / `TdxZs` / `TdxBk` / `TdxHy`
- `TdxClient` 新增（同步 + 异步同构）：
  `get_zhb_files()` / `get_tdx_stat()` / `get_tdx_stat2()` / `get_xgsg()` /
  `get_spblock()` / `get_tdx_zs()` / `get_tdx_bk()` / `get_tdx_hy()`
- 字段语义照搬 injoyai/tdx 的实盘核验注释；未核验字段保留 `_fields`。
- 测试：真实 zhb 成员存 fixture，离线解析单测。

### M2 · T3 派生计算（低风险，纯逻辑）
- 新增 `derive/adjust.py`：gbbq → 前/后复权**仿射因子**，对任意 K 线施加 QFQ/HFQ
- 新增 `derive/basic.py`：前收盘、换手率、市值（股本 + 日K）
- `TdxClient` 新增：`get_adjust_factors()` / `qfq()` / `hfq()` / `get_basic_daily()`
- 依据 tdx2db `calc/` 的 QUANTAXIS 复权算法。

### M3 · T2 7615 F10（价值最大）
- 新增 `f10/transport.py`：TQLEX HTTP 客户端（timeout / retry / IPv4 优先）
- 新增 `f10/entries.py`：Entry 常量 + 参数构造
- 新增 `f10/models.py`：`F10Response` / `F10ResultSet`
- 新增 `f10/client.py`：`F10Client` + 高层方法
- 首批 Entry：`company_profile` / `finance_report` / `valuation` /
  `business_composition` / `dividend_financing` / `hot_topics` /
  `announcements` / `northbound_holding`
- `TdxClient.f10` 懒加载属性。

### M4 · T2 第二批 Entry
- `stock_score` / `profit_forecast` / `ranking_detail` / `governance` /
  `company_news` / `limit_up_down_list` / `theme_market`

### M5 · T4 Helpers（可选）
- `auction_data` / `shortline_indicators` / `stock_profile_table`

## 工程约定
- T1/T3 返回 `DataFrame`；F10 返回 `F10Response`（JSON 结构多样，不强塞 DataFrame）
- 新 7709 命令统一走 `_execute_std`（自动回退到全功能主机）
- 解析层无 IO，便于离线单测；同步 / 异步接口保持同构
- 保留原始字段（`_fields` / `raw`），命名保守
- 测试：`tests/unit` 离线 fixture + `XMTDX_LIVE` 门控联网测试
- ruff / mypy strict 通过

## 风险
- zhb 文件集随版本变化 → 解析容错，缺失文件跳过
- 7615 公共网关可能限流 / 变更 → timeout / retry / 可配 base_url
- 字段无官方文档 → 保留原始字段
- 主机能力差异（已知）→ 复用自动回退

## 实施状态

| 阶段 | 状态 | 交付 |
| --- | --- | --- |
| M1 · T1 配置类加工 | ✅ 已完成 | `codec/configdata.py`、`models/configdata.py`、客户端 8 个方法、10 单测 |
| M2 · T3 派生计算 | ✅ 已完成 | `derive/adjust.py`、`derive/basic.py`、客户端 3 个方法、7 单测 |
| M3 · T2 F10 首批 | ✅ 已完成 | `f10/`（transport/parse/models/entries/client）、`TdxClient.f10`、8 单测 |
| M4 · T2 F10 二批 | ✅ 已完成 | stock_score/profit_forecast/ranking_detail/governance/company_news/limit_up_down_list/theme_market/allotment/topic_compare |
| M5 · T4 Helpers | ⚠️ 部分 | `get_stock_profile`（行情+股本+市值+换手+估值）已完成；`auction_data` 用现有 `MacClient.get_auction`；`shortline_indicators`（竞价/开盘量比/封单/连板）**未实现** |
| M5 · T5 落库 | ⏸ 未做 | DuckDB/ClickHouse ETL 与 `bfq/qfq/hfq` 视图（tdx2db 模式）**未实现**，依赖独立存储层，建议单独排期 |

### 实测（真实服务器）
- tdxstat 8042 行；spblock 中证2000 = 2000；tdxhy 5659 行
- 本地 gbbq 复权 vs MAC 服务端 QFQ：60 根，max diff 0.10 / mean 0.0017
- 换手率 600519 = 0.1101%、000001 = 0.3892%（与已知口径一致）
- F10 16 个 Entry 全部返回数据（公司概况/财报 102 期/题材/公告 99 条/北向/涨停榜 84 条…）

### 未实现（明确记录）
1. `shortline_indicators`：依赖竞价 + 开盘量比 + 封单 + 连板等多源组合，逻辑复杂，暂缓。
2. T5 落库：需要引入 DuckDB/ClickHouse 依赖，超出"协议库"边界，建议作为独立项目。
3. 7615 未封装的其余 Entry：可用 `F10Client.call(entry, params=[...])` 手动调用。

