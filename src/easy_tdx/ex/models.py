"""扩展行情数据模型与常量。"""

from dataclasses import dataclass, field

from ..config import get_ex_hosts, get_mac_ex_hosts

# 模块级别名，供外部 `from easy_tdx.ex.models import KNOWN_EX_HOSTS` 使用。
KNOWN_EX_HOSTS = get_ex_hosts()

# 已知扩展行情市场代码
KNOWN_EX_MARKETS: dict[int, str] = {
    0: "深圳",
    1: "上海",
    28: "郑州商品",
    29: "大连商品",
    30: "上海期货",
    31: "香港主板",
    47: "中金所",
    48: "香港创业板",
    49: "香港基金",
    71: "沪港通",
    74: "外盘",
}

# MAC 协议扩展行情服务器（端口 7727）
MAC_EX_HOSTS: list[str] = get_mac_ex_hosts()

_DEFAULT_EX_PORT = 7727


@dataclass
class ExMarketInfo:
    """市场定义（GetMarkets 返回）。"""

    market: int
    category: int
    name: str
    short_name: str
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentInfo:
    """合约/证券信息（GetInstrumentInfo 返回）。"""

    category: int
    market: int
    code: str
    name: str
    desc: str
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentQuote:
    """五档行情（GetInstrumentQuote 返回）。"""

    market: int
    code: str
    pre_close: float
    open: float
    high: float
    low: float
    price: float
    kaicang: int
    zongliang: int
    xianliang: int
    neipan: int
    waipan: int
    chicang: int
    bid1: float
    bid2: float
    bid3: float
    bid4: float
    bid5: float
    bid_vol1: int
    bid_vol2: int
    bid_vol3: int
    bid_vol4: int
    bid_vol5: int
    ask1: float
    ask2: float
    ask3: float
    ask4: float
    ask5: float
    ask_vol1: int
    ask_vol2: int
    ask_vol3: int
    ask_vol4: int
    ask_vol5: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExInstrumentBar:
    """K线数据（GetInstrumentBars / GetHistoryInstrumentBarsRange 返回）。"""

    open: float
    high: float
    low: float
    close: float
    position: int
    trade: int
    amount: float
    year: int
    month: int
    day: int
    hour: int
    minute: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExMinuteBar:
    """分时数据（GetMinuteTimeData / GetHistoryMinuteTimeData 返回）。"""

    hour: int
    minute: int
    price: float
    avg_price: float
    volume: int
    open_interest: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExTransactionRecord:
    """逐笔成交记录（GetTransactionData / GetHistoryTransactionData 返回）。"""

    hour: int
    minute: int
    second: int
    price: int
    volume: int
    zengcang: int
    nature: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExServerInfo:
    """扩展市场服务器信息（0x2455）。"""

    delay: int
    info: str
    version: str
    server_sign: str
    server_sign2: str
    time_now: str
    server_name: str
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class ExTableChunk:
    """扩展市场表格分块（0x2422 / 0x2423）。"""

    start: int
    count: int
    content: str
    _raw: bytes = field(default=b"", repr=False, compare=False)
