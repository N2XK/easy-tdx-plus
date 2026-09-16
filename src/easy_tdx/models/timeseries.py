"""分时与逐笔成交模型"""

from dataclasses import dataclass, field


@dataclass
class MinuteBar:
    """今日/历史分时（每分钟一条，共 240 条）

    unknown_1: 协议中第二个变长整数，含义未明（疑似均价的编码形式）。
    """

    price: float  # 价格
    vol: int  # 成交量

    # pytdx 中被完全丢弃的字段，保留以供分析
    _unknown_1: int = field(default=0, repr=False)  # 原 reversed1

    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class MinuteAuxPoint:
    """分时副图数据点（0x051b，240 点）。

    - ``buy_sell_strength`` 口径：``buy`` / ``sell`` 为买卖力道（协议为 u8）。
    - ``volume_comparison`` 口径：``series_a`` / ``series_b`` 为成交对比两条序列（f32）。
    """

    index: int
    buy: int = 0
    sell: int = 0
    series_a: float = 0.0
    series_b: float = 0.0
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class SparklineSeries:
    """小走势图序列（0x0fd1）。"""

    market: int
    code: str
    selector: int
    max_count: int
    base_price: float
    prices: list[float] = field(default_factory=list)
    _raw: bytes = field(default=b"", repr=False, compare=False)


@dataclass
class TransactionRecord:
    """逐笔成交记录

    unknown_last: pytdx 中被 _ 丢弃的最后一个变长整数，保留以供分析。
    时间精度仅到分钟（协议限制），unknown_last 可能含秒或序号信息。
    """

    hour: int
    minute: int
    price: float
    vol: int
    buyorsell: int  # 0=买, 1=卖, 2=中性/撮合, 8=集合竞价

    # pytdx 中被丢弃的字段
    unknown_last: int = field(default=0, repr=False)

    _raw: bytes = field(default=b"", repr=False, compare=False)
