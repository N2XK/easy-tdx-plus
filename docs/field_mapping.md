> ⚠️ **本文件为旧版（v0.1.1）遗留文档，可能已过时。最新、完整的接口清单见 [数据字典](数据字典.md)。**

# easy_tdx 字段映射表

> 模型字段名 ↔ 中文含义 ↔ 数据类型对照

---

## SecurityInfo（证券列表条目）

来源：`get_security_list()` / `get_security_list_all()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `market` | 市场 | `Market` | SZ=深圳, SH=上海, BJ=北京 |
| `code` | 证券代码 | `str` | 6 位代码，如 "600000" |
| `name` | 证券名称 | `str` | GBK 解码 |
| `volunit` | 成交量单位 | `int` | 1 手 = volunit 股 |
| `decimal_point` | 价格小数位 | `int` | 通常为 2 |
| `pre_close` | 昨收价 | `float` | 通达信自定义浮点 |
| `industry_tdx` | 通达信行业 | `str` | 如 "T1001"，需 `get_security_list_all()` |
| `industry_sw` | 申万行业 | `str` | 如 "X500102"，需 `get_security_list_all()` |

---

## SecurityQuote（实时五档行情）

来源：`get_security_quotes()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `market` | 市场 | `Market` | |
| `code` | 证券代码 | `str` | |
| `price` | 现价 | `float` | 当前最新成交价 |
| `pre_close` | 昨收价 | `float` | 昨日收盘价 |
| `open` | 今开 | `float` | 今日开盘价 |
| `high` | 最高 | `float` | 今日最高价 |
| `low` | 最低 | `float` | 今日最低价 |
| `vol` | 总成交量 | `float` | 单位：手 |
| `cur_vol` | 当前成交量 | `float` | |
| `amount` | 成交额 | `float` | 单位：元 |
| `s_vol` | 内盘 | `float` | 主动卖出成交量 |
| `b_vol` | 外盘 | `float` | 主动买入成交量 |
| `active1` | 活跃度1 | `int` | 含义待确认 |
| `active2` | 活跃度2 | `int` | 含义待确认 |
| `bid1` ~ `bid5` | 买一~买五价 | `float` | |
| `bid_vol1` ~ `bid_vol5` | 买一~买五量 | `float` | |
| `ask1` ~ `ask5` | 卖一~卖五价 | `float` | |
| `ask_vol1` ~ `ask_vol5` | 卖一~卖五量 | `float` | |
| `rise_speed` | 涨速 | `float` | |
| `limit_up` | 涨停价 | `float \| None` | 需 `get_price_limits()` 计算 |
| `limit_down` | 跌停价 | `float \| None` | 需 `get_price_limits()` 计算 |
| `server_time` | 服务器时间 | `str` | 格式 HH:MM:SS.mmm |

---

## SecurityBar（K 线数据）

来源：`get_security_bars()` / `get_index_bars()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `open` | 开盘价 | `float` | |
| `close` | 收盘价 | `float` | |
| `high` | 最高价 | `float` | |
| `low` | 最低价 | `float` | |
| `vol` | 成交量 | `float` | 单位：股 |
| `amount` | 成交额 | `float` | 单位：元 |
| `year` | 年 | `int` | |
| `month` | 月 | `int` | |
| `day` | 日 | `int` | |
| `hour` | 时 | `int` | 日线为 0 |
| `minute` | 分 | `int` | 日线为 0 |
| `datetime_str` | 时间字符串 | `str` | 属性，格式 YYYY-MM-DD HH:MM |

---

## MinuteBar（分时数据）

来源：`get_minute_time_data()` / `get_history_minute_time_data()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `price` | 价格 | `float` | |
| `vol` | 成交量 | `int` | |

---

## TransactionRecord（逐笔成交）

来源：`get_transaction_data()` / `get_history_transaction_data()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `hour` | 时 | `int` | |
| `minute` | 分 | `int` | |
| `price` | 成交价 | `float` | |
| `vol` | 成交量 | `int` | |
| `buyorsell` | 买卖方向 | `int` | 0=买, 1=卖, 2=中性, 8=集合竞价 |

---

## XdxrRecord（除权除息记录）

来源：`get_xdxr_info()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `market` | 市场 | `Market` | |
| `code` | 证券代码 | `str` | |
| `year` | 年 | `int` | |
| `month` | 月 | `int` | |
| `day` | 日 | `int` | |
| `category` | 事件类型 | `int` | 见 XDXR_CATEGORY_NAMES |
| `name` | 事件名称 | `str` | |
| `fenhong` | 每股分红 | `float \| None` | 元，category=1 |
| `peigujia` | 配股价 | `float \| None` | 元/股，category=1 |
| `songzhuangu` | 每股送转股比例 | `float \| None` | category=1 |
| `peigu` | 每股配股比例 | `float \| None` | category=1 |
| `suogu` | 缩股比例 | `float \| None` | category=11,12 |
| `xingquanjia` | 行权价 | `float \| None` | category=13,14 |
| `fenshu` | 分数 | `float \| None` | category=13,14 |
| `panqian_liutong` | 盘前流通股本 | `float \| None` | 万股，category=2~10 |
| `panhou_liutong` | 盘后流通股本 | `float \| None` | 万股，category=2~10 |
| `qian_zongguben` | 前总股本 | `float \| None` | 万股，category=2~10 |
| `hou_zongguben` | 后总股本 | `float \| None` | 万股，category=2~10 |

### XDXR_CATEGORY_NAMES（事件类型映射）

| category | 名称 |
|----------|------|
| 1 | 除权除息 |
| 2 | 送配股上市 |
| 3 | 非流通股上市 |
| 4 | 未知股本变动 |
| 5 | 股本变化 |
| 6 | 增发新股 |
| 7 | 股份回购 |
| 8 | 增发新股上市 |
| 9 | 转配股上市 |
| 10 | 可转债上市 |
| 11 | 扩缩股 |
| 12 | 非流通股缩股 |
| 13 | 送认购权证 |
| 14 | 送认沽权证 |

---

## FinanceInfo（最新财务数据）

来源：`get_finance_info()`

### 股本结构（单位：万股）

| 字段名 | 中文 |
|--------|------|
| `liutong_guben` | 流通股本 |
| `zong_guben` | 总股本 |
| `guojia_gu` | 国家股 |
| `faqiren_faren_gu` | 发起人法人股 |
| `faren_gu` | 法人股 |
| `b_gu` | B股 |
| `h_gu` | H股 |
| `zhigong_gu` | 职工股 |

### 基本信息

| 字段名 | 中文 | 类型 |
|--------|------|------|
| `province` | 省份代码 | `int` |
| `industry` | 行业代码 | `int` |
| `updated_date` | 财务更新日期 | `int` | YYYYMMDD |
| `ipo_date` | 上市日期 | `int` | YYYYMMDD |
| `gudong_renshu` | 股东人数 | `float` |

### 资产负债（单位：元）

| 字段名 | 中文 |
|--------|------|
| `zong_zichan` | 总资产 |
| `liudong_zichan` | 流动资产 |
| `guding_zichan` | 固定资产 |
| `wuxing_zichan` | 无形资产 |
| `liudong_fuzhai` | 流动负债 |
| `changqi_fuzhai` | 长期负债 |
| `ziben_gongjijin` | 资本公积金 |
| `jing_zichan` | 净资产 |

### 利润指标（单位：元）

| 字段名 | 中文 |
|--------|------|
| `zhuying_shouru` | 主营收入 |
| `zhuying_lirun` | 主营利润 |
| `yingshou_zhangkuan` | 应收账款 |
| `yingye_lirun` | 营业利润 |
| `touzi_shouyu` | 投资收益 |
| `jingying_xianjinliu` | 经营现金流 |
| `zong_xianjinliu` | 总现金流 |
| `cunhuo` | 存货 |
| `lirun_zonghe` | 利润总额 |
| `shuihou_lirun` | 税后利润 |
| `jing_lirun` | 净利润 |
| `weifen_lirun` | 未分配利润 |

### 每股指标

| 字段名 | 中文 | 说明 |
|--------|------|------|
| `meigujing_zichan` | 每股净资产 | 原协议字段 baoliu1 |

---

## CompanyInfoCategory（公司信息目录）

来源：`get_company_info_category()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `name` | 目录名 | `str` | 如 "最新提示" |
| `filename` | 文件名 | `str` | 如 "600000.txt" |
| `start` | 起始偏移 | `int` | 字节偏移 |
| `length` | 内容长度 | `int` | 字节数 |

---

## TdxBlock（板块信息）

来源：`get_block_info()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `name` | 板块名称 | `str` | 如 "房地产" |
| `category` | 板块分类 | `int` | 0=行业, 1=地域, 2=概念, 3=风格 |
| `count` | 成分股数 | `int` | |
| `codes` | 成分股代码 | `list[str]` | 6 位代码列表 |

---

## MarketStat（市场统计）

来源：`get_market_stat()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `up_count` | 上涨家数 | `int` | |
| `down_count` | 下跌家数 | `int` | |
| `neutral_count` | 平盘家数 | `int` | |
| `suspended_count` | 停牌(估算) | `int` | 残差：total - up - down - neutral |
| `total_count` | 总计 | `int` | |
| `total_amount` | 总成交额 | `float` | 元 |
| `total_volume` | 总成交量 | `float` | |
| `total_market_cap` | 总市值 | `float` | 元，880001 price × 1e10 |
| `limit_up_count` | 涨停家数 | `int` | 880006 price |
| `limit_down_count` | 跌停家数 | `int` | 880006 open |

---

## FundFlow（资金流向）

来源：`get_fund_flow()`

| 字段名 | 中文 | 类型 | 说明 |
|--------|------|------|------|
| `super_in` | 超大单流入 | `float` | 单笔 >100 万 |
| `super_out` | 超大单流出 | `float` | |
| `large_in` | 大单流入 | `float` | 20~100 万 |
| `large_out` | 大单流出 | `float` | |
| `medium_in` | 中单流入 | `float` | 4~20 万 |
| `medium_out` | 中单流出 | `float` | |
| `small_in` | 小单流入 | `float` | ≤4 万 |
| `small_out` | 小单流出 | `float` | |
| `main_net_inflow` | 主力净流入 | `float` | 属性：超大+大 |
| `total_net_inflow` | 全单净流入 | `float` | 属性：全部 |

---

## HistoricalFundFlow（历史资金流向）

来源：`get_history_fund_flow()`

字段同 FundFlow，额外包含：

| 字段名 | 中文 | 类型 |
|--------|------|------|
| `year` | 年 | `int` |
| `month` | 月 | `int` |
| `day` | 日 | `int` |

---

## 枚举

### Market（市场）

| 值 | 名称 | 说明 |
|----|------|------|
| 0 | SZ | 深圳 |
| 1 | SH | 上海 |
| 2 | BJ | 北京 |

### KlineCategory（K 线周期）

| 值 | 名称 | 说明 |
|----|------|------|
| 0 | MIN_5 | 5 分钟 |
| 1 | MIN_15 | 15 分钟 |
| 2 | MIN_30 | 30 分钟 |
| 3 | MIN_60 | 60 分钟 |
| 4 | DAY | 日线 |
| 5 | WEEK | 周线 |
| 6 | MONTH | 月线 |
| 7 | MIN_1 | 1 分钟 |
| 8 | MIN_3 | 3 分钟（内部用） |
| 9 | YEAR | 年线 |
| 10 | SEASON | 季线 |
| 11 | YEAR_ALT | 年线（备用） |
