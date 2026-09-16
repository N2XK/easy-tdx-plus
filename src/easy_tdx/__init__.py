"""easy_tdx — 通达信 TCP 协议 A 股行情数据客户端。

快速开始::

    from easy_tdx import TdxClient, Market, KlineCategory

    with TdxClient("180.153.18.170") as c:
        count = c.get_security_count(Market.SH)
        bars  = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)

asyncio 版本::

    import asyncio
    from easy_tdx import AsyncTdxClient, Market, KlineCategory

    async def main():
        async with AsyncTdxClient("180.153.18.170") as c:
            bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 5)

    asyncio.run(main())
"""

from ._df import to_tuples
from .capabilities import FEATURES, probe_capabilities
from .client import AsyncTdxClient, TdxClient
from .config import save_best_ex_host, save_best_host
from .derive import add_indicators, boll, ema, evaluate, kdj, ma, macd, rsi, volume_ratio
from .downloader import Downloader
from .ex.client import AsyncExTdxClient, ExTdxClient
from .ex.mac_client import AsyncMacExClient, MacExClient
from .ex.models import KNOWN_EX_HOSTS
from .exceptions import (
    TdxCommandError,
    TdxConnectionError,
    TdxDecodeError,
    TdxError,
    TdxValidationError,
)
from .f10 import (
    AltF10Client,
    AsyncF10Client,
    AsyncIcfqsClient,
    F10Client,
    F10Response,
    F10ResultSet,
    IcfqsClient,
)
from .fund import classify_fund, is_fund
from .mac.client import AsyncMacClient, MacClient
from .mac.enums import (
    Adjust,
    BoardType,
    Category,
    ExMarket,
    FilterType,
    Period,
    SortOrder,
    SortType,
)
from .models import (
    XDXR_CATEGORY_NAMES,
    CompanyInfoCategory,
    FinanceInfo,
    FinancialFileInfo,
    FinancialRecord,
    KlineCategory,
    Market,
    MinuteBar,
    SecurityBar,
    SecurityInfo,
    SecurityQuote,
    TransactionRecord,
    XdxrRecord,
)
from .parallel import ParallelTdx
from .ratelimit import AsyncRateLimiter, RateLimiter, detect_phase
from .trading_calendar import TradingCalendar
from .transport.sync import CALC_HOSTS, KNOWN_HOSTS, MAC_HOSTS, ping_all, ping_mac_all
from .unified import AsyncUnifiedTdxClient, UnifiedTdxClient
from .validation import check_bars, validate_bars

__all__ = [
    # 客户端
    "TdxClient",
    "AsyncTdxClient",
    "F10Client",
    "AltF10Client",
    "AsyncF10Client",
    "F10Response",
    "F10ResultSet",
    "IcfqsClient",
    "AsyncIcfqsClient",
    "MacClient",
    "AsyncMacClient",
    "MacExClient",
    "AsyncMacExClient",
    "UnifiedTdxClient",
    "AsyncUnifiedTdxClient",
    # 枚举
    "Market",
    "KlineCategory",
    "Adjust",
    "BoardType",
    "Category",
    "ExMarket",
    "FilterType",
    "Period",
    "SortOrder",
    "SortType",
    # 数据模型
    "SecurityBar",
    "SecurityQuote",
    "SecurityInfo",
    "MinuteBar",
    "TransactionRecord",
    "XdxrRecord",
    "XDXR_CATEGORY_NAMES",
    "FinanceInfo",
    "CompanyInfoCategory",
    "FinancialFileInfo",
    "FinancialRecord",
    # 异常
    "TdxError",
    "TdxConnectionError",
    "TdxDecodeError",
    "TdxCommandError",
    "TdxValidationError",
    # 扩展行情
    "ExTdxClient",
    "AsyncExTdxClient",
    "KNOWN_EX_HOSTS",
    # 工具
    "ping_all",
    "ping_mac_all",
    "ParallelTdx",
    "Downloader",
    "TradingCalendar",
    "probe_capabilities",
    "FEATURES",
    "RateLimiter",
    "AsyncRateLimiter",
    "detect_phase",
    "to_tuples",
    "classify_fund",
    "is_fund",
    "check_bars",
    "validate_bars",
    # 技术指标
    "add_indicators",
    "ma",
    "ema",
    "macd",
    "kdj",
    "boll",
    "rsi",
    "volume_ratio",
    "evaluate",
    "KNOWN_HOSTS",
    "CALC_HOSTS",
    "MAC_HOSTS",
    "save_best_host",
    "save_best_ex_host",
]

__version__ = "1.1.0"
