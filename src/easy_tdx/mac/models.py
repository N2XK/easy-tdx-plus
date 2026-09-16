"""MAC 协议数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass(frozen=True)
class MacQuoteField:
    """MAC 协议自定义字段报价中的一条记录。"""

    market: int
    code: str
    name: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MacSymbolInfo:
    """个股简要特征。"""

    market: int
    code: str
    name: str
    time: datetime | None
    activity: int
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    momentum: float
    vol: int
    amount: float
    inside_volume: int
    outside_volume: int
    turnover: float
    avg: float


@dataclass(frozen=True)
class MacBar:
    """MAC 协议 K 线数据。"""

    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    vol: float
    amount: float
    float_shares: float = 0.0


@dataclass(frozen=True)
class MacTick:
    """分时数据点。"""

    time: time
    price: float
    avg: float
    vol: int
    momentum: float = 0.0


@dataclass(frozen=True)
class MacTickChart:
    """单日分时图。"""

    market: int
    code: str
    name: str
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    vol: int
    amount: float
    turnover: float = 0.0
    avg: float = 0.0
    charts: list[MacTick] = field(default_factory=list)


@dataclass(frozen=True)
class MacMultiTickDay:
    """多日分时图中的一天。"""

    date: date
    pre_close: float
    ticks: list[MacTick] = field(default_factory=list)


@dataclass(frozen=True)
class MacMultiTickChart:
    """多日分时图。"""

    market: int
    code: str
    name: str
    pre_close: float
    open: float
    high: float
    low: float
    close: float
    vol: int
    amount: float
    turnover: float = 0.0
    avg: float = 0.0
    charts: list[MacMultiTickDay] = field(default_factory=list)


@dataclass(frozen=True)
class MacTransaction:
    """逐笔成交。"""

    time: time
    price: float
    vol: int
    trade_count: int
    bs_flag: int  # 0=买入 / 1=卖出 / 2=中性 / 5=盘后


@dataclass(frozen=True)
class BoardInfo:
    """板块信息。"""

    market: int
    code: str
    name: str
    price: float
    rise_speed: float
    pre_close: float
    symbol_market: int
    symbol_code: str
    symbol_name: str
    symbol_price: float
    symbol_rise_speed: float
    symbol_pre_close: float


@dataclass(frozen=True)
class AuctionItem:
    """集合竞价数据。"""

    time: time
    price: float
    matched: int
    unmatched: int


@dataclass(frozen=True)
class UnusualItem:
    """异动数据。"""

    index: int
    market: int
    code: str
    name: str
    time: time
    desc: str
    value: str
    unusual_type: int


@dataclass(frozen=True)
class CapitalFlowData:
    """资金流向数据（0x1218 head=2, Query=Stock_ZJLX）。

    字段口径与 gotdx ``mac_capital_flow.go`` 一致：

    - **今日**：``[主力买, 主力卖, 散户买, 散户卖]`` → ``main_*`` / ``small_*``
    - **近 5 日**：``[主力买, 主力卖, 超大单净, 大单净, 中单净, 小单净]``
      → ``main_buy_5d`` / ``main_sell_5d`` / ``super_large_net_5d`` /
      ``large_net_5d`` / ``medium_net_5d`` / ``small_net_5d``

    ``date`` 服务端未提供，留空。
    """

    date: str
    # 今日
    main_in: float = 0.0
    main_out: float = 0.0
    main_net: float = 0.0
    small_in: float = 0.0
    small_out: float = 0.0
    small_net: float = 0.0
    # 近 5 日
    main_buy_5d: float = 0.0
    main_sell_5d: float = 0.0
    main_net_5d: float = 0.0
    super_large_net_5d: float = 0.0
    large_net_5d: float = 0.0
    medium_net_5d: float = 0.0
    small_net_5d: float = 0.0


@dataclass(frozen=True)
class BelongBoardInfo:
    """个股所属板块信息。"""

    board_type: int
    market: int
    board_code: str
    board_name: str
    close: float
    pre_close: float


@dataclass(frozen=True)
class ServerSession:
    """服务器交易时段信息。"""

    today: str
    last_trading_day: str
    sessions_1: list[dict[str, Any]] = field(default_factory=list)
    sessions_2: list[dict[str, Any]] = field(default_factory=list)
    market_param_1: int = 0
    market_param_2: int = 0


@dataclass(frozen=True)
class CategoryCodeItem:
    """代码/分类索引条目（0x124A）。

    35 字节定长记录：``flag(1) | code(6,ASCII) | name(8,GBK) | mark(8) |
    abbr(8,ASCII) | flags(u32)``。

    - ``abbr`` 为**拼音缩写**（如 000001 平安银行 → ``PAYH``），可用于拼音检索；
    - ``mark`` 通常为 0，仅 1 条特殊记录（399354 分析师指）为 ``0xFDCA``；
    - ``flags`` 为分类位掩码：bit9(0x200) 恒置位，其余位与代码段相关
      （395xxx→0x200、399xxx→0x10200、深市股票→0x1010200/0x10200），确切语义未确证；
    - ``_raw`` 保留原始 35 字节。
    """

    flag: int
    code: str
    name: str
    abbr: str
    mark: int = 0
    flags: int = 0
    _raw: bytes = field(default=b"", repr=False, compare=False)


class KlineOffsetInfo:
    """0x124A 响应头部信息（保留兼容）。

    ``total``：服务端回显的请求 count（小 count 时无数据）；``returned``：随后的
    分类代码记录条数。
    """

    total: int
    returned: int
