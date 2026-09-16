"""证券扩展特征 / 指数信息模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SecurityFeature:
    """证券扩展特征（0x0452）：特殊品种涨跌停限制等。"""

    market: int
    code: str
    p1: float
    p2: float
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class IndexInfoOrder:
    """指数概况中的委托分布档位。"""

    price: float
    unknown: int
    vol: int


@dataclass
class IndexInfo:
    """指数概况（0x051d）。"""

    market: int
    code: str
    active: int
    close: float
    pre_close: float
    diff: float
    open: float
    high: float
    low: float
    server_time: str
    vol: int
    cur_vol: int
    amount: float
    open_amount: int
    up_count: int
    down_count: int
    orders: list[IndexInfoOrder] = field(default_factory=list)
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class TopBoardItem:
    """排行榜条目（0x053f）。"""

    category: str
    market: int
    code: str
    price: float
    value: float
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class VolumeProfileItem:
    """成交分布档位（0x051a）。"""

    price: float
    vol: int
    buy: int
    sell: int


@dataclass
class VolumeProfile:
    """个股成交分布（0x051a）。"""

    market: int
    code: str
    active: int
    close: float
    pre_close: float
    open: float
    high: float
    low: float
    server_time: str
    neg_price: float
    vol: int
    cur_vol: int
    amount: float
    in_vol: int
    out_vol: int
    s_amount: int
    open_amount: int
    bids: list[tuple[float, int]] = field(default_factory=list)
    asks: list[tuple[float, int]] = field(default_factory=list)
    profiles: list[VolumeProfileItem] = field(default_factory=list)
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class EncryptedQuote:
    """加密批量行情条目（0x0547）。"""

    market: int
    code: str
    active: int
    close: float
    pre_close: float
    open: float
    high: float
    low: float
    vol: int
    cur_vol: int
    amount: float
    in_vol: int
    out_vol: int
    s_amount: int
    open_amount: int
    bids: list[tuple[float, int]] = field(default_factory=list)
    asks: list[tuple[float, int]] = field(default_factory=list)
    _raw: bytes = field(default=b"", repr=False, compare=False)
