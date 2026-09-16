"""高层行情 API：TdxClient（同步）和 AsyncTdxClient（asyncio）。"""

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, TypeVar, cast
from zoneinfo import ZoneInfo

import pandas as pd

from ._df import (
    _add_minute_aux_time,
    _add_minute_datetime,
    _merge_bar_datetime,
    _merge_txn_datetime,
    _to_df,
)
from .codec.block import parse_block_dat
from .codec.configdata import (
    fill_block_index_with_alias,
    parse_spblock,
    parse_tdxbk,
    parse_tdxhy,
    parse_tdxstat,
    parse_tdxstat2,
    parse_tdxzs,
    parse_xgsg,
    unzip_zhb,
)
from .codec.financial import parse_financial_dat, parse_financial_file_list
from .codec.industry import parse_tdxhy_cfg
from .codec.price_rules import compute_price_limits, get_no_limit_window_days
from .commands.base import BaseCommand
from .commands.block_info import GetBlockInfoCmd, GetBlockInfoMetaCmd
from .commands.company_info import GetCompanyInfoCategoryCmd, GetCompanyInfoContentCmd
from .commands.finance_info import GetFinanceInfoCmd
from .commands.fund_flow import GetHistoryFundFlowCmd
from .commands.index_info import GetIndexInfoCmd
from .commands.index_momentum import GetIndexMomentumCmd
from .commands.minute_aux import GetMinuteAuxCmd, resolve_selector
from .commands.minute_time import GetHistoryMinuteTimeDataCmd
from .commands.quotes_encrypt import GetQuotesEncryptCmd
from .commands.report_file import GetReportFileCmd
from .commands.security_bars import GetIndexBarsCmd, GetSecurityBarsCmd
from .commands.security_count import GetSecurityCountCmd
from .commands.security_feature import GetSecurityFeatureCmd
from .commands.security_list import GetSecurityListCmd
from .commands.security_quotes import GetSecurityQuotesCmd
from .commands.sparkline import GetSparklineCmd
from .commands.top_board import GetTopBoardCmd
from .commands.transaction import GetHistoryTransactionDataCmd, GetTransactionDataCmd
from .commands.volume_profile import GetVolumeProfileCmd
from .commands.xdxr_info import GetXdxrInfoCmd
from .config import (
    get_best_host,
    get_calc_hosts,
    get_full_featured_hosts,
    get_known_hosts,
    get_port,
    get_retry_delays,
    get_timeout,
    save_best_host,
)
from .derive import adjust_bars, compute_adjust_factors, compute_basic_daily, evaluate
from .exceptions import TdxConnectionError, TdxDecodeError
from .f10 import F10Client, IcfqsClient
from .fund import is_fund
from .models.bar import SecurityBar
from .models.configdata import SpBlock
from .models.enums import KlineCategory, Market
from .models.feature import IndexInfo, VolumeProfile
from .models.finance import (
    FinancialFileInfo,
    FinancialRecord,
)
from .models.security import SecurityInfo
from .models.stats import FundFlow, HistoricalFundFlow, MarketStat
from .models.timeseries import TransactionRecord
from .ratelimit import AsyncRateLimiter, RateLimiter
from .trading_calendar import TradingCalendar
from .transport.async_ import AsyncTdxConnection
from .transport.sync import TdxConnection, ping_all

_T = TypeVar("_T")
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
_DAILY_PLUS = frozenset(
    {
        KlineCategory.DAY,
        KlineCategory.WEEK,
        KlineCategory.MONTH,
        KlineCategory.YEAR,
        KlineCategory.YEAR_ALT,
    }
)


def _today_in_shanghai() -> int:
    return int(datetime.now(_SHANGHAI_TZ).strftime("%Y%m%d"))


def _paginate(
    fetch: Callable[[int, int], pd.DataFrame],
    count: int,
    max_pages: int = 256,
) -> pd.DataFrame:
    """通用分页：反复调用 fetch(start, count) 直到返回空页或不足一页。"""
    frames: list[pd.DataFrame] = []
    start = 0
    for _ in range(max_pages):
        page = fetch(start, count)
        if page is None or page.empty:
            break
        frames.append(page)
        start += len(page)
        if len(page) < count:
            break
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


async def _paginate_async(
    fetch: Callable[[int, int], Awaitable[pd.DataFrame]],
    count: int,
    max_pages: int = 256,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    start = 0
    for _ in range(max_pages):
        page = await fetch(start, count)
        if page is None or page.empty:
            break
        frames.append(page)
        start += len(page)
        if len(page) < count:
            break
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _looks_like_index(market: Market, code: str) -> bool:
    """按市场与代码前缀判断是否为指数（用于 K 线自动路由）。"""
    if market == Market.SH:
        return code.startswith(("000", "880", "881", "882", "883", "884", "885", "999"))
    if market == Market.SZ:
        return code.startswith(("395", "399"))
    return False


def _infer_market(code: str) -> Market:
    """按代码前缀推断市场（尽力而为，与 pytdx.get_k_data 一致）。

    仅覆盖常见股票/基金代码；指数（如 000001 既是上证指数又是平安银行）
    请使用显式 market 的接口。
    """
    return Market.SH if code[:1] in {"5", "6", "9"} else Market.SZ


def _bar_date_column(df: pd.DataFrame) -> str:
    return "date" if "date" in df.columns else "datetime"


def _validate_yyyymmdd(value: int, name: str) -> None:
    text = str(value)
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"{name} 需为 YYYYMMDD 格式的整数，收到: {value!r}")


# 在延迟优选时，最多探测前 N 台主机的标准协议能力，避免选用旧版/纯报价服务器。
_STD_PROBE_LIMIT = 6
# 主机标准协议能力探测结果缓存（进程内，带 TTL）。
_STD_CAPABILITY_CACHE: dict[str, tuple[float, bool]] = {}
_STD_CAPABILITY_TTL = 3600.0


def _probe_standard_capability(host: str, port: int, timeout: float) -> bool:
    """探测主机是否支持标准协议实时行情。

    通达信存在旧版/纯报价服务器，能完成握手但不响应实时行情等新命令。
    用一次真实行情请求作为能力探针，用于 from_best_host 的服务器优选。
    结果按主机缓存（进程内），避免每次重连重复探测。
    """
    key = f"{host}:{port}"
    cached = _STD_CAPABILITY_CACHE.get(key)
    if cached is not None and (time.monotonic() - cached[0]) < _STD_CAPABILITY_TTL:
        return cached[1]
    try:
        conn = TdxConnection(host, port, timeout)
        conn.connect()
        try:
            quotes = conn.execute(GetSecurityQuotesCmd([(Market.SH, "600519")]))
        finally:
            conn.close()
        result = bool(quotes)
    except Exception:
        result = False
    _STD_CAPABILITY_CACHE[key] = (time.monotonic(), result)
    return result


def _record_signature(
    record: TransactionRecord,
) -> tuple[int, int, float, int, int, int]:
    return (
        record.hour,
        record.minute,
        record.price,
        record.vol,
        record.buyorsell,
        record.unknown_last,
    )


def _page_signature(
    records: list[TransactionRecord],
) -> tuple[tuple[int, int, float, int, int, int], tuple[int, int, float, int, int, int]]:
    return (_record_signature(records[0]), _record_signature(records[-1]))


def _classify_fund_flow(records: list[TransactionRecord]) -> FundFlow:
    stats = {
        "super_in": 0.0,
        "large_in": 0.0,
        "medium_in": 0.0,
        "small_in": 0.0,
        "super_out": 0.0,
        "large_out": 0.0,
        "medium_out": 0.0,
        "small_out": 0.0,
    }

    for record in records:
        amount = record.price * record.vol * 100.0
        direction = "in" if record.buyorsell == 0 else "out" if record.buyorsell == 1 else None
        if not direction:
            continue

        if amount > 1_000_000:
            stats[f"super_{direction}"] += amount
        elif amount > 200_000:
            stats[f"large_{direction}"] += amount
        elif amount > 40_000:
            stats[f"medium_{direction}"] += amount
        else:
            stats[f"small_{direction}"] += amount

    return FundFlow(**stats)


def _date_from_bar(bar: SecurityBar) -> int:
    return bar.year * 10000 + bar.month * 100 + bar.day


def _historical_fund_flow_from_records(
    date: int, records: list[TransactionRecord]
) -> HistoricalFundFlow:
    flow = _classify_fund_flow(records)
    year = date // 10000
    month = (date // 100) % 100
    day = date % 100
    return HistoricalFundFlow(
        year=year,
        month=month,
        day=day,
        super_in=flow.super_in,
        super_out=flow.super_out,
        large_in=flow.large_in,
        large_out=flow.large_out,
        medium_in=flow.medium_in,
        medium_out=flow.medium_out,
        small_in=flow.small_in,
        small_out=flow.small_out,
    )


# ============================================================
# 同步客户端
# ============================================================

_CACHE_DIR = Path.home() / ".easy_tdx" / "cache"
_CACHE_MAX_AGE = 86400  # 1 天


def _serialize_stocks(stocks: list[SecurityInfo]) -> list[dict[str, Any]]:
    return [{k: v for k, v in asdict(s).items() if k != "_raw"} for s in stocks]


def _deserialize_stocks(data: list[dict[str, Any]]) -> list[SecurityInfo]:
    return [SecurityInfo(**{**d, "market": Market(d["market"])}) for d in data]


def _load_cache() -> list[SecurityInfo] | None:
    path = _CACHE_DIR / "security_list_all.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text("utf-8"))
        updated = datetime.fromisoformat(raw["updated"])
        if (datetime.now() - updated).total_seconds() > _CACHE_MAX_AGE:
            return None
        return _deserialize_stocks(raw["data"])
    except Exception:
        return None


def _save_cache(stocks: list[SecurityInfo]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "updated": datetime.now().isoformat(),
        "count": len(stocks),
        "data": _serialize_stocks(stocks),
    }
    (_CACHE_DIR / "security_list_all.json").write_text(
        json.dumps(data, ensure_ascii=False), "utf-8"
    )


class TdxClient:
    """同步通达信行情客户端，支持 IP 优选与断线自动重连。

    使用示例::

        # 单台服务器
        with TdxClient("180.153.18.170") as c:
            bars = c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)

        # 自动从候选列表中选延迟最低的服务器
        with TdxClient.from_best_host() as c:
            count = c.get_security_count(Market.SH)
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 15.0,
        rate_limit: bool = False,
        retry_delays: tuple[float, ...] | None = None,
    ) -> None:
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._retry_delays = retry_delays if retry_delays is not None else get_retry_delays()
        self._conn = TdxConnection(host, port, timeout)
        self._zhb_cache: dict[str, bytes] | None = None
        self._f10: F10Client | None = None
        self._icfqs: IcfqsClient | None = None
        self._limiter: RateLimiter | None = RateLimiter() if rate_limit else None
        if self._limiter is not None:
            self._limiter.auto_detect_phase()

    def set_phase(self, phase: str) -> None:
        """设置限流时段（仅当启用 ``rate_limit`` 时有效）。"""
        if self._limiter is not None:
            self._limiter.set_phase(phase)

    def auto_detect_phase(self) -> str | None:
        """按当前时间自动检测限流时段。"""
        return self._limiter.auto_detect_phase() if self._limiter is not None else None

    def _rate_acquire(self) -> None:
        if self._limiter is not None:
            self._limiter.acquire()

    @property
    def f10(self) -> F10Client:
        """7615 F10 / TQLEX 客户端（懒加载，走独立 HTTP 网关）。"""
        if self._f10 is None:
            self._f10 = F10Client()
        return self._f10

    @property
    def icfqs(self) -> IcfqsClient:
        """ICFQS 7615 客户端：龙虎榜 / 游资 / 每日复盘 / 题材（懒加载）。"""
        if self._icfqs is None:
            self._icfqs = IcfqsClient()
        return self._icfqs

    # ------------------------------------------------------------------ #
    # 工厂方法：自动优选最低延迟服务器
    # ------------------------------------------------------------------ #

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float | None = None,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 15.0,
    ) -> "TdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟且支持标准协议的建立连接。

        自动将最佳主机保存到 config.json，后续连接默认使用该主机。
        若所有服务器均不可达，回退到 hosts[0]。
        """
        if hosts is None:
            hosts = get_known_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        # 在最快的若干台主机中，优先选择支持标准协议的全功能服务器
        for host, _latency in ranked[:_STD_PROBE_LIMIT]:
            if _probe_standard_capability(host, port, timeout):
                best = host
                break
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        if hosts is None:
            hosts = get_known_hosts()
        if port is None:
            port = get_port()
        return ping_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        self._conn.connect()
        if self._heartbeat_interval > 0:
            self._conn.start_heartbeat(self._heartbeat_interval)

    def close(self) -> None:
        self._conn.stop_heartbeat()
        self._conn.close()

    def disconnect(self) -> None:
        """Alias for close()."""
        self.close()

    def ensure_connected(self) -> None:
        """验证连接存活，断线则自动重建。"""
        try:
            self._execute(GetSecurityCountCmd(Market.SH))
        except TdxConnectionError:
            self._conn.stop_heartbeat()
            self._conn.close()
            self._conn = TdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            if self._heartbeat_interval > 0:
                self._conn.start_heartbeat(self._heartbeat_interval)

    def __enter__(self) -> "TdxClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # 内部执行：含自动重连
    # ------------------------------------------------------------------ #

    def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        """执行命令；断线时指数退避重试。"""
        self._rate_acquire()
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError as first_exc:
            if not self._auto_reconnect:
                raise
            last_exc: TdxConnectionError = first_exc
            for delay in self._retry_delays:
                time.sleep(delay)
                self._conn.close()
                self._conn = TdxConnection(self._host, self._port, self._timeout)
                self._conn.connect()
                if self._heartbeat_interval > 0:
                    self._conn.start_heartbeat(self._heartbeat_interval)
                try:
                    return self._conn.execute(cmd)
                except TdxConnectionError as e:
                    last_exc = e
            raise last_exc

    def _switch_host(self, host: str) -> None:
        """将底层连接切换到指定主机，并持久化为最佳主机。"""
        self._conn.close()
        self._host = host
        self._conn = TdxConnection(host, self._port, self._timeout)
        self._conn.connect()
        if self._heartbeat_interval > 0:
            self._conn.start_heartbeat(self._heartbeat_interval)
        save_best_host(host)

    def _reconnect(self) -> None:
        """关闭并重建到当前主机的连接。"""
        self._conn.close()
        self._conn = TdxConnection(self._host, self._port, self._timeout)
        self._conn.connect()
        if self._heartbeat_interval > 0:
            self._conn.start_heartbeat(self._heartbeat_interval)

    def _execute_std(self, cmd: "BaseCommand[_T]", *, require_nonempty: bool = False) -> _T:
        """执行标准协议数据命令，自动避开不支持该命令的服务器。

        通达信存在旧版/纯报价服务器，不响应实时行情、逐笔成交、标准协议
        K 线等命令，会返回残缺响应（解码失败）或空结果。若当前服务器出现
        这两种情况，则依次尝试全功能主机，成功后复用该主机。

        Args:
            require_nonempty: 为 True 时空结果也视为异常并触发回退
                （适用于正常必有数据的命令，如行情、逐笔成交）。
        """
        empty_result: Any = None
        last_exc: TdxDecodeError | None
        try:
            result = self._execute(cmd)
            if result or not require_nonempty:
                return result
            empty_result = result
            last_exc = None
        except TdxDecodeError as exc:
            empty_result = None
            last_exc = exc

        for host in get_full_featured_hosts():
            if host == self._host:
                continue
            try:
                conn = TdxConnection(host, self._port, self._timeout)
                conn.connect()
                try:
                    result = conn.execute(cmd)
                finally:
                    conn.close()
            except Exception:
                continue
            if result or not require_nonempty:
                self._switch_host(host)
                return result
            empty_result = result
            last_exc = None

        if last_exc is not None:
            raise last_exc
        return cast("_T", empty_result)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    def get_security_count(self, market: Market) -> int:
        """获取市场证券总数。"""
        return self._execute(GetSecurityCountCmd(market))

    def get_security_list(self, market: Market, start: int) -> pd.DataFrame:
        """获取证券列表（每页约1000条，按 start 分页）。"""
        return _to_df(self._execute(GetSecurityListCmd(market, start)))

    def get_security_list_all(self, pages: int | str = "all") -> pd.DataFrame:
        """获取沪深 A 股完整证券列表，并自动挂载行业信息。

        Args:
            pages: 拉取页数。每个市场每页 1000 条。
                   "all" 拉取全部（默认，结果会缓存到本地文件）。
                   整数 N 表示每个市场只拉前 N 页，不缓存。

        注意：
            `Market.BJ` 的证券列表请求长期存在服务器超时问题，当前版本暂不纳入此方法。
        """
        log = logging.getLogger(__name__)

        if pages == "all":
            cached = _load_cache()
            if cached is not None:
                log.info("从缓存加载沪深 A 股列表，共 %d 只", len(cached))
                return _to_df(cached)

        # 计算每个市场的最大起始偏移
        def _max_start(count: int) -> int:
            if pages == "all":
                return count
            return min(count, int(pages) * 1000)

        # 尝试获取行业配置
        industry_map: dict[str, tuple[str, str]] = {}
        try:
            cfg_data = self.get_report_file("tdxhy.cfg")
            if cfg_data:
                industry_map = parse_tdxhy_cfg(cfg_data)
                log.info("行业配置已加载，共 %d 条映射", len(industry_map))
        except Exception:
            log.warning("无法获取 tdxhy.cfg，行业字段将为空")

        all_stocks: list[SecurityInfo] = []
        for market in [Market.SH, Market.SZ]:
            count = self.get_security_count(market)
            limit = _max_start(count)
            total_pages = (limit + 999) // 1000
            for page_idx, start in enumerate(range(0, limit, 1000)):
                try:
                    stocks = self._execute(GetSecurityListCmd(market, start))
                except Exception:
                    log.warning(
                        "%s 第 %d/%d 页获取失败，跳过", market.name, page_idx + 1, total_pages
                    )
                    continue
                log.info(
                    "%s 第 %d/%d 页: %d 条", market.name, page_idx + 1, total_pages, len(stocks)
                )
                for s in stocks:
                    is_a_share = (market == Market.SH and s.code.startswith(("60", "68"))) or (
                        market == Market.SZ and s.code.startswith(("00", "30"))
                    )
                    if is_a_share:
                        if s.code in industry_map:
                            s.industry_tdx, s.industry_sw = industry_map[s.code]
                        all_stocks.append(s)

        log.info("沪深 A 股总数: %d", len(all_stocks))

        if pages == "all":
            _save_cache(all_stocks)

        return _to_df(all_stocks)

    def get_fund_list(self, market: Market, pages: int | str = "all") -> pd.DataFrame:
        """获取基金列表（ETF/LOF/REITs/分级/债券基金，按代码前缀识别）。

        Args:
            pages: "all" 拉取全部；整数 N 只拉前 N 页（每页 1000 条）。
        """
        count = self.get_security_count(market)
        limit = count if pages == "all" else min(count, int(pages) * 1000)
        funds: list[SecurityInfo] = []
        for start in range(0, limit, 1000):
            try:
                stocks = self._execute(GetSecurityListCmd(market, start))
            except Exception:
                continue
            funds.extend(s for s in stocks if is_fund(s.code))
        return _to_df(funds)

    def get_security_quotes(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        """批量获取实时五档行情（最多80只/次）。"""
        return _to_df(self._execute_std(GetSecurityQuotesCmd(stocks), require_nonempty=True))

    def get_quotes_encrypt(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        """加密批量行情（0x0547，最多 100 只，含完整五档）。"""
        return _to_df(self._execute_std(GetQuotesEncryptCmd(stocks), require_nonempty=True))

    def get_price_limits(
        self, market: Market, code: str, name: str, pre_close: float
    ) -> tuple[float | None, float | None]:
        """按当前交易状态计算涨跌停价。

        对上市初期不设涨跌幅限制的标的，会先用日 K 线条数估算已上市交易天数。
        """
        listed_days: int | None = None
        no_limit_window_days = get_no_limit_window_days(market, code, name)
        if no_limit_window_days > 0:
            try:
                bars = self._execute(
                    GetSecurityBarsCmd(market, code, KlineCategory.DAY, 0, no_limit_window_days + 1)
                )
                listed_days = len(bars)
            except Exception:
                listed_days = None

        return compute_price_limits(
            market,
            code,
            name,
            pre_close,
            listed_days=listed_days,
        )

    # ------------------------------------------------------------------ #
    # K 线
    # ------------------------------------------------------------------ #

    def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        """获取 K 线数据（最多800条/次，按 start 分页）。"""
        df = _to_df(
            self._execute_std(
                GetSecurityBarsCmd(market, code, category, start, count), require_nonempty=True
            )
        )
        return _merge_bar_datetime(df, category in _DAILY_PLUS)

    def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        """获取指数 K 线数据。"""
        df = _to_df(
            self._execute_std(
                GetIndexBarsCmd(market, code, category, start, count), require_nonempty=True
            )
        )
        return _merge_bar_datetime(df, category in _DAILY_PLUS)

    def get_security_features(self, start: int = 0, count: int = 2000) -> pd.DataFrame:
        """证券扩展特征（0x0452，特殊品种涨跌停限制表等）。"""
        return _to_df(self._execute_std(GetSecurityFeatureCmd(start, count), require_nonempty=True))

    def get_index_momentum(self, market: Market, code: str) -> pd.DataFrame:
        """指数动量（0x051c，累计值序列）。"""
        values = self._execute_std(GetIndexMomentumCmd(market, code), require_nonempty=True)
        return pd.DataFrame({"momentum": values})

    def get_index_info(self, market: Market, code: str) -> IndexInfo:
        """指数概况（0x051d，含涨跌家数与委托分布）。"""
        return self._execute_std(GetIndexInfoCmd(market, code))

    def get_top_board(self, size: int = 20, category: int = 0) -> pd.DataFrame:
        """排行榜（0x053f，9 组榜单：涨幅/跌幅/振幅/涨速/量比/委比/换手）。"""
        items = self._execute_std(GetTopBoardCmd(category, size), require_nonempty=True)
        return _to_df(items)

    def get_volume_profile(self, market: Market, code: str) -> VolumeProfile:
        """个股成交分布（0x051a，Volume Profile）。"""
        return self._execute_std(GetVolumeProfileCmd(market, code))

    def get_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        """按市场与代码自动路由股票或指数 K 线。"""
        if _looks_like_index(market, code):
            return self.get_index_bars(market, code, category, start, count)
        return self.get_security_bars(market, code, category, start, count)

    def get_bars_range(
        self,
        market: Market,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
        count: int = 800,
    ) -> pd.DataFrame:
        """分页获取日期闭区间 [start_date, end_date] 内的 K 线（升序、去重）。

        Args:
            start_date / end_date: YYYYMMDD 整数。
            category: K 线周期，默认日线。
        """
        _validate_yyyymmdd(start_date, "start_date")
        _validate_yyyymmdd(end_date, "end_date")
        if start_date > end_date:
            raise ValueError("start_date 不能晚于 end_date")

        frames: list[pd.DataFrame] = []
        page_start = 0
        empty = pd.DataFrame()
        for _ in range(256):
            page = self.get_bars(market, code, category, page_start, count)
            if page.empty:
                break
            col = _bar_date_column(page)
            days = pd.to_datetime(page[col]).dt.strftime("%Y%m%d").astype(int)
            mask = (days >= start_date) & (days <= end_date)
            if mask.any():
                frames.append(page.loc[mask])
            if int(days.min()) <= start_date or len(page) < count:
                break
            page_start += len(page)
            empty = page.iloc[0:0]

        if not frames:
            return empty
        result = pd.concat(frames, ignore_index=True)
        col = _bar_date_column(result)
        result = result.drop_duplicates(subset=[col]).sort_values(col).reset_index(drop=True)
        return result

    def get_trading_calendar(
        self,
        start_date: int = 19900101,
        end_date: int | None = None,
        *,
        market: Market = Market.SH,
        code: str = "000001",
        category: KlineCategory = KlineCategory.DAY,
    ) -> TradingCalendar:
        """由指数日线构建交易日历（默认上证指数）。

        不内置节假日表，交易日来自真实 K 线，因此天然正确。
        """
        if end_date is None:
            end_date = _today_in_shanghai()
        bars = self.get_bars_range(market, code, start_date, end_date, category)
        return TradingCalendar.from_bars(bars)

    def get_trading_days(
        self,
        start_date: int = 19900101,
        end_date: int | None = None,
        *,
        market: Market = Market.SH,
        code: str = "000001",
        category: KlineCategory = KlineCategory.DAY,
    ) -> list[date]:
        """返回 [start_date, end_date] 内的交易日（升序）。"""
        return self.get_trading_calendar(
            start_date, end_date, market=market, code=code, category=category
        ).days

    def get_k_data(
        self,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
    ) -> pd.DataFrame:
        """便捷获取某代码日期区间内的 K 线（自动推断市场，默认日线）。

        与 pytdx 的 ``get_k_data`` 保持一致：仅按代码前缀推断所属市场
        （6/5/9 开头为上海，其余为深圳），指数请改用显式 market 的接口。
        """
        return self.get_bars_range(_infer_market(code), code, start_date, end_date, category)

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: Market, code: str) -> pd.DataFrame:
        """获取今日分时数据（240条，走历史分时接口）。"""
        today = _today_in_shanghai()
        bars = self._execute(GetHistoryMinuteTimeDataCmd(market, code, today))
        return _add_minute_datetime(_to_df(bars), today)

    def get_history_minute_time_data(self, market: Market, code: str, date: int) -> pd.DataFrame:
        """获取历史某日分时数据（date: YYYYMMDD）。"""
        bars = self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))
        return _add_minute_datetime(_to_df(bars), date)

    def get_recent_minute_time_data(self, market: Market, code: str, days: int = 5) -> pd.DataFrame:
        """获取最近 N 个交易日的分时数据（逐日拉取 0x0fb4）。

        等价于 eltdx 的 ``minutes.recent``：以每日一次请求覆盖近期窗口，
        数据与 ``get_history_minute_time_data`` 相同（含完整 datetime）。
        """
        daily = self.get_bars(market, code, KlineCategory.DAY, 0, days)
        if daily.empty:
            return pd.DataFrame()
        dates = sorted(int(pd.Timestamp(d).strftime("%Y%m%d")) for d in daily["date"])
        frames = [self.get_history_minute_time_data(market, code, d) for d in dates]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def get_minute_aux(
        self, market: Market, code: str, kind: str | int = "buy_sell_strength"
    ) -> pd.DataFrame:
        """获取分时副图（0x051b），240 点。

        Args:
            kind: ``"buy_sell_strength"``（买卖力道）或 ``"volume_comparison"``
                （成交对比），也可直接传 selector 数字。
        """
        selector = resolve_selector(kind)
        points = self._execute_std(GetMinuteAuxCmd(market, code, selector), require_nonempty=True)
        volume_compare = selector == resolve_selector("volume_comparison")
        rows = [
            (
                {"index": p.index, "series_a": p.series_a, "series_b": p.series_b}
                if volume_compare
                else {"index": p.index, "buy": p.buy, "sell": p.sell}
            )
            for p in points
        ]
        return _add_minute_aux_time(pd.DataFrame(rows))

    def get_sparkline(
        self, market: Market, code: str, selector: int = 1, window: int = 20
    ) -> pd.DataFrame:
        """小走势图（0x0fd1）：轻量价格序列。

        返回含 ``price`` 列的 DataFrame，``base_price`` 存于 ``df.attrs``。

        注：该命令在单个 TCP 连接上仅响应一次，故每次调用前重建连接。
        """
        self._reconnect()
        series = self._execute_std(
            GetSparklineCmd(market, code, selector, window), require_nonempty=True
        )
        df = pd.DataFrame({"price": series.prices})
        df.attrs["base_price"] = series.base_price
        return df

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> pd.DataFrame:
        """获取当日逐笔成交（分页）。"""
        df = _to_df(
            self._execute_std(
                GetTransactionDataCmd(market, code, start, count), require_nonempty=True
            )
        )
        return _merge_txn_datetime(df, _today_in_shanghai())

    def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> pd.DataFrame:
        """获取历史逐笔成交（date: YYYYMMDD，分页）。"""
        df = _to_df(
            self._execute_std(
                GetHistoryTransactionDataCmd(market, code, date, start, count),
                require_nonempty=True,
            )
        )
        return _merge_txn_datetime(df, date)

    def get_history_transaction_all(
        self, market: Market, code: str, date: int, count: int = 800
    ) -> pd.DataFrame:
        """获取某历史日的**全部**逐笔成交（自动分页）。

        免去了 g3tic/g4tic `.htc` 全市场大文件解析：直接按 (日期, 个股) 拉取，
        实测服务器可回溯多年。同一时刻的完全相同成交为真实数据，故不去重。
        """
        frames: list[pd.DataFrame] = []
        start = 0
        while True:
            page = self.get_history_transaction_data(market, code, date, start, count)
            if page is None or page.empty:
                break
            frames.append(page)
            start += len(page)
            if len(page) < count:
                break
        if not frames:
            return pd.DataFrame()
        out = pd.concat(frames, ignore_index=True)
        return out.sort_values("datetime").reset_index(drop=True)

    def get_security_features_all(self, count: int = 2000) -> pd.DataFrame:
        """获取全部证券扩展特征（0x0452，特殊品种涨跌停限制表等），自动分页。"""
        return _paginate(lambda s, c: self.get_security_features(s, c), count)

    # ------------------------------------------------------------------ #
    # 财务 / 公司
    # ------------------------------------------------------------------ #

    def get_xdxr_info(self, market: Market, code: str) -> pd.DataFrame:
        """获取除权除息历史记录。"""
        return _to_df(self._execute(GetXdxrInfoCmd(market, code)))

    def get_finance_info(self, market: Market, code: str) -> pd.DataFrame:
        """获取最新财务数据。"""
        return _to_df(self._execute(GetFinanceInfoCmd(market, code)))

    def get_company_info_category(self, market: Market, code: str) -> pd.DataFrame:
        """获取公司信息文件目录。"""
        return _to_df(self._execute(GetCompanyInfoCategoryCmd(market, code)))

    def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        """读取公司信息文本。"""
        return self._execute(GetCompanyInfoContentCmd(market, code, filename, offset, length))

    def get_block_info(self, filename: str) -> pd.DataFrame:
        """获取并解析板块文件（行业、概念、风格等）。

        常用文件名：
          'block_zs.dat'  - 行业/指数板块
          'block_gn.dat'  - 概念板块
          'block_fg.dat'  - 风格板块
        """
        size, _hash = self._execute(GetBlockInfoMetaCmd(filename))
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while pos < size:
            chunk = self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
        return _to_df(parse_block_dat(bytes(full_data), filename))

    def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件（如 'base_info.zip'）。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while True:
            chunk = self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
        return bytes(full_data)

    # ------------------------------------------------------------------ #
    # 配置类加工数据（zhb.zip / tdxhy.cfg）
    # ------------------------------------------------------------------ #

    def get_zhb_files(self) -> dict[str, bytes]:
        """下载并解压 zhb.zip，返回 {文件名: 原始字节}（结果缓存于实例）。

        zhb.zip 含 46 个配置文件（tdxstat.cfg / spblock.dat / tdxzs.cfg /
        tdxbk.cfg / xgsg.cfg 等），是配置类加工数据的来源。
        """
        if self._zhb_cache is not None:
            return self._zhb_cache
        self._zhb_cache = unzip_zhb(self.get_report_file("zhb.zip"))
        return self._zhb_cache

    def _zhb_member(self, filename: str) -> bytes:
        return self.get_zhb_files().get(filename, b"")

    def get_tdx_stat(self) -> pd.DataFrame:
        """个股综合统计（tdxstat.cfg）：PE(TTM)/静态PE/股息率/连涨跌/区间涨幅等。"""
        return _to_df(parse_tdxstat(self._zhb_member("tdxstat.cfg")))

    def get_tdx_stat2(self) -> pd.DataFrame:
        """个股资金流向 + 板块归属（tdxstat2.cfg）：成交额/IPO价/52周高低/板块指数。"""
        return _to_df(parse_tdxstat2(self._zhb_member("tdxstat2.cfg")))

    def get_xgsg(self) -> pd.DataFrame:
        """新股申购（xgsg.cfg）：申购代码/日期/发行价/名称。"""
        return _to_df(parse_xgsg(self._zhb_member("xgsg.cfg")))

    def get_spblock(self, fill_index: bool = True) -> list[SpBlock]:
        """专业板块成分（spblock.dat），如 中证2000/1000/500 等大型指数。

        Args:
            fill_index: 是否用 tdxzs/tdxbk 回填板块指数代码到 ``SpBlock.index``。
        """
        blocks = parse_spblock(self._zhb_member("spblock.dat"))
        if fill_index and blocks:
            zs = parse_tdxzs(self._zhb_member("tdxzs.cfg"))
            bk = parse_tdxbk(self._zhb_member("tdxbk.cfg"))
            fill_block_index_with_alias(blocks, zs, bk)
        return blocks

    def get_tdx_zs(self) -> pd.DataFrame:
        """板块指数配置（tdxzs.cfg）：板块名称 → 指数代码。"""
        return _to_df(parse_tdxzs(self._zhb_member("tdxzs.cfg")))

    def get_tdx_bk(self) -> pd.DataFrame:
        """板块简称↔全称（tdxbk.cfg）。"""
        return _to_df(parse_tdxbk(self._zhb_member("tdxbk.cfg")))

    def get_tdx_hy(self) -> pd.DataFrame:
        """行业归属（tdxhy.cfg）：通达信行业 + 申万行业。"""
        return _to_df(parse_tdxhy(self.get_report_file("tdxhy.cfg")))

    # ------------------------------------------------------------------ #
    # 派生计算（复权 / 基础指标）
    # ------------------------------------------------------------------ #

    def _daily_bars_with_xdxr(
        self, market: Market, code: str, start_date: int, end_date: int
    ) -> tuple[pd.DataFrame, list[Any]]:
        bars = self.get_bars_range(market, code, start_date, end_date, KlineCategory.DAY)
        events = self._execute(GetXdxrInfoCmd(market, code))
        return bars, events

    def get_adjust_factors(
        self, market: Market, code: str, start_date: int = 19900101, end_date: int | None = None
    ) -> pd.DataFrame:
        """计算与日线对齐的前/后复权因子（基于 gbbq 除权除息事件）。"""
        if end_date is None:
            end_date = _today_in_shanghai()
        bars, events = self._daily_bars_with_xdxr(market, code, start_date, end_date)
        return compute_adjust_factors(bars, events)

    def get_fq_bars(
        self,
        market: Market,
        code: str,
        mode: str = "qfq",
        start_date: int = 19900101,
        end_date: int | None = None,
    ) -> pd.DataFrame:
        """获取前复权（qfq）/ 后复权（hfq）日线（本地按 gbbq 计算）。

        替代：MAC 协议 ``get_stock_kline(adjust=...)`` 由服务端计算，两者口径略有差异。
        """
        if end_date is None:
            end_date = _today_in_shanghai()
        bars, events = self._daily_bars_with_xdxr(market, code, start_date, end_date)
        return adjust_bars(bars, events, mode=mode)

    def get_basic_daily(
        self,
        market: Market,
        code: str,
        start_date: int = 19900101,
        end_date: int | None = None,
        float_shares: float | None = None,
        total_shares: float | None = None,
    ) -> pd.DataFrame:
        """每日基础指标：前收盘 / 涨跌幅 / 振幅 / 换手率 / 市值。

        股本默认取最新财务数据（单位：股）；如需历史股本请自行传入。
        """
        if end_date is None:
            end_date = _today_in_shanghai()
        bars, events = self._daily_bars_with_xdxr(market, code, start_date, end_date)
        if float_shares is None or total_shares is None:
            fin = self.get_finance_info(market, code)
            if not fin.empty:
                if float_shares is None:
                    float_shares = float(fin.iloc[0].get("liutong_guben", 0.0) or 0.0)
                if total_shares is None:
                    total_shares = float(fin.iloc[0].get("zong_guben", 0.0) or 0.0)
        return compute_basic_daily(
            bars,
            events,
            float_shares=float_shares or 0.0,
            total_shares=total_shares or 0.0,
        )

    def get_formula(
        self,
        market: Market,
        code: str,
        formula: str,
        start_date: int = 19900101,
        end_date: int | None = None,
        category: KlineCategory = KlineCategory.DAY,
    ) -> pd.DataFrame:
        """在个股 K 线上计算通达信公式（指标/选股）。

        Args:
            formula: 通达信公式文本，如 ``"MA5: MA(CLOSE,5); G: CROSS(MA5, REF(MA5,1));"``。
        """
        if end_date is None:
            end_date = _today_in_shanghai()
        bars = self.get_bars_range(market, code, start_date, end_date, category)
        return evaluate(formula, bars)

    def get_stock_profile(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        """股票信息汇总：行情 + 股本 + 市值 + 换手率 + 估值（PE/股息率）。

        组合实时行情（标准协议）、最新财务（股本）、tdxstat（PE/股息）。
        """
        quotes = self.get_security_quotes(stocks)
        if quotes.empty:
            return quotes
        stat = self.get_tdx_stat()
        stat_map = (
            stat.set_index("code")[["pe_ttm", "pe_static", "div_yield"]] if not stat.empty else None
        )
        rows: list[dict[str, Any]] = []
        for (mkt, code), (_, q) in zip(stocks, quotes.iterrows()):
            fin = self.get_finance_info(mkt, code)
            float_shares = float(fin.iloc[0].get("liutong_guben", 0.0)) if not fin.empty else 0.0
            total_shares = float(fin.iloc[0].get("zong_guben", 0.0)) if not fin.empty else 0.0
            price = float(q["price"])
            vol = float(q["vol"])  # 标准行情 vol 单位为手
            vol_shares = vol * 100
            rec: dict[str, Any] = {
                "market": int(mkt),
                "code": code,
                "price": price,
                "pre_close": float(q["pre_close"]),
                "change_pct": round((price / float(q["pre_close"]) - 1) * 100, 2)
                if q["pre_close"]
                else None,
                "open": float(q["open"]),
                "high": float(q["high"]),
                "low": float(q["low"]),
                "vol": vol,
                "amount": float(q["amount"]),
                "float_shares": float_shares,
                "total_shares": total_shares,
                "turnover_pct": round(vol_shares / float_shares * 100, 4) if float_shares else None,
                "float_mv": round(price * float_shares, 2) if float_shares else None,
                "total_mv": round(price * total_shares, 2) if total_shares else None,
            }
            if stat_map is not None and code in stat_map.index:
                s = stat_map.loc[code]
                rec["pe_ttm"] = float(s["pe_ttm"])
                rec["pe_static"] = float(s["pe_static"])
                rec["div_yield"] = float(s["div_yield"])
            rows.append(rec)
        return pd.DataFrame(rows)

    @staticmethod
    def _download_from_host(
        host: str, filename: str, port: int = 7709, timeout: float = 15.0
    ) -> bytes:
        """从指定服务器创建临时连接并下载文件。"""
        conn = TdxConnection(host, port, timeout)
        try:
            conn.connect()
            full_data = bytearray()
            pos = 0
            chunk_size = 30000
            while True:
                chunk = conn.execute(GetReportFileCmd(filename, pos, chunk_size))
                if not chunk:
                    break
                full_data.extend(chunk)
                pos += len(chunk)
                if len(chunk) < chunk_size:
                    break
            return bytes(full_data)
        finally:
            conn.close()

    def get_financial_file_list(self, host: str | None = None) -> pd.DataFrame:
        """获取可用的历史专业财报文件列表。

        连接到计算服务器，下载 tdxfin/gpcw.txt 并解析。
        """
        if host is None:
            host = get_calc_hosts()[0]
        data = self._download_from_host(host, "tdxfin/gpcw.txt")
        raw_list = parse_financial_file_list(data)
        return _to_df([FinancialFileInfo(filename=f, hash=h, filesize=s) for f, h, s in raw_list])

    def get_financial_file(self, filename: str, host: str | None = None) -> bytes:
        """从计算服务器下载财报 zip 文件。

        Args:
            filename: 如 'tdxfin/gpcw20260331.zip'
        """
        if host is None:
            host = get_calc_hosts()[0]
        return self._download_from_host(host, filename)

    def get_financial_records(self, filename: str, host: str | None = None) -> pd.DataFrame:
        """下载财报 zip 并解析为每只股票的记录列表。

        Args:
            filename: 如 'tdxfin/gpcw20260331.zip'
        """
        if host is None:
            host = get_calc_hosts()[0]
        import io
        import re
        import zipfile

        zip_data = self.get_financial_file(filename, host)
        if not zip_data:
            return pd.DataFrame()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            dat_names = [n for n in zf.namelist() if n.endswith(".dat")]
            if not dat_names:
                return pd.DataFrame()
            dat_data = zf.read(dat_names[0])

        m = re.search(r"(\d{8})", filename)
        report_date = int(m.group(1)) if m else 0

        raw_records = parse_financial_dat(dat_data, report_date)
        records: list[FinancialRecord] = []
        for code, market_byte, rdate, fields in raw_records:
            market = Market.SH if market_byte == 1 else Market.SZ
            records.append(
                FinancialRecord(code=code, market=market, report_date=rdate, fields=fields)
            )
        return _to_df(records)

    def get_market_stat(self) -> pd.DataFrame:
        """获取 A 股全市场涨跌统计概况（基于 880005 行情统计）。

        注意：
            `suspended_count` 是 `total - up - down - neutral` 的残差估算值，
            用于保证计数守恒，不应视为协议已明确验证的停牌字段。
        """
        # 通达信中 880005 是全市场行情统计，880001 是总市值指数，880006 是涨跌停统计
        quotes = self._execute(
            GetSecurityQuotesCmd(
                [(Market.SH, "880005"), (Market.SH, "880001"), (Market.SH, "880006")]
            )
        )
        if not quotes:
            raise RuntimeError("无法获取市场统计数据")
        q = quotes[0]
        up = int(q.price)
        down = int(q.open)
        neutral = int(q.low)
        total = int(q.high)
        market_cap = quotes[1].price * 1e10 if len(quotes) > 1 else 0.0
        limit_down = int(quotes[2].open) if len(quotes) > 2 else 0
        limit_up = int(quotes[2].price) if len(quotes) > 2 else 0
        return _to_df(
            MarketStat(
                up_count=up,
                down_count=down,
                neutral_count=neutral,
                suspended_count=max(0, total - up - down - neutral),
                total_count=total,
                total_amount=q.amount,
                total_volume=q.vol,
                total_market_cap=market_cap,
                limit_up_count=limit_up,
                limit_down_count=limit_down,
            )
        )

    def _collect_transaction_records(
        self,
        fetch_page: Callable[[int, int], list[TransactionRecord]],
        page_size: int,
        max_start: int = 10000,
    ) -> list[TransactionRecord]:
        all_recs: list[TransactionRecord] = []
        seen_sig: set[tuple[int, int, float, int, int, int]] = set()
        seen_page_sigs: set[
            tuple[
                tuple[int, int, float, int, int, int],
                tuple[int, int, float, int, int, int],
            ]
        ] = set()
        start = 0

        while start < max_start:
            recs = fetch_page(start, page_size)
            if not recs:
                break

            page_sig = _page_signature(recs)
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            new_count = 0
            for record in recs:
                sig = _record_signature(record)
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    all_recs.append(record)
                    new_count += 1

            if new_count == 0:
                break

            start += len(recs)
            if len(recs) < 100:
                break

        return all_recs

    def get_fund_flow(self, market: Market, code: str) -> pd.DataFrame:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        records = self._collect_transaction_records(
            lambda start, page_size: self._execute(
                GetTransactionDataCmd(market, code, start, page_size)
            ),
            2000,
        )
        return _to_df(_classify_fund_flow(records))

    def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> pd.DataFrame:
        """获取个股历史日线资金流向序列。

        优先走 Category 22 直连接口；若服务器返回空列表，则自动回退为
        "日 K 线取日期 + 历史逐笔成交重算资金流"的兼容实现。
        """
        try:
            direct = self._execute(GetHistoryFundFlowCmd(market, code, start, count))
        except Exception:
            direct = []
        if direct:
            return _to_df(direct)

        bars = self._execute(GetSecurityBarsCmd(market, code, KlineCategory.DAY, start, count))
        results: list[HistoricalFundFlow] = []
        for bar in bars:
            date = _date_from_bar(bar)
            records = self._collect_transaction_records(
                lambda page_start, page_size: self._execute(
                    GetHistoryTransactionDataCmd(market, code, date, page_start, page_size)
                ),
                800,
            )
            results.append(_historical_fund_flow_from_records(date, records))
        return _to_df(results)


# ============================================================
# 异步客户端
# ============================================================


class AsyncTdxClient:
    """异步通达信行情客户端（asyncio）。

    使用示例::

        async with AsyncTdxClient("180.153.18.170") as c:
            bars = await c.get_security_bars(Market.SH, "600000", KlineCategory.DAY, 0, 100)

    注意：
        单个 AsyncTdxClient 仅维护一条 TCP 连接；并发调用会在连接内串行执行。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
        rate_limit: bool = False,
        retry_delays: tuple[float, ...] | None = None,
    ) -> None:
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._retry_delays = retry_delays if retry_delays is not None else get_retry_delays()
        self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._zhb_cache: dict[str, bytes] | None = None
        self._limiter: AsyncRateLimiter | None = AsyncRateLimiter() if rate_limit else None
        if self._limiter is not None:
            self._limiter.auto_detect_phase()

    def set_phase(self, phase: str) -> None:
        """设置限流时段（仅当启用 ``rate_limit`` 时有效）。"""
        if self._limiter is not None:
            self._limiter.set_phase(phase)

    def auto_detect_phase(self) -> str | None:
        """按当前时间自动检测限流时段。"""
        return self._limiter.auto_detect_phase() if self._limiter is not None else None

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float | None = None,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> "AsyncTdxClient":
        """测量 hosts 中所有服务器延迟，选最低延迟的建立连接。

        自动将最佳主机保存到 config.json。
        """
        if hosts is None:
            hosts = get_known_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        # 在最快的若干台主机中，优先选择支持标准协议的全功能服务器
        for host, _latency in ranked[:_STD_PROBE_LIMIT]:
            if _probe_standard_capability(host, port, timeout):
                best = host
                break
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        if hosts is None:
            hosts = get_known_hosts()
        if port is None:
            port = get_port()
        return ping_all(hosts, port, timeout)

    async def connect(self) -> None:
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
        await self._conn.close()

    async def __aenter__(self) -> "AsyncTdxClient":
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    def _start_heartbeat(self) -> None:
        """启动后台心跳任务。"""
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """停止并清理心跳任务。"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """心跳循环：定期发送轻量级请求保活。"""
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                # 使用 get_security_count 作为心跳包
                await self.get_security_count(Market.SH)
            except asyncio.CancelledError:
                break
            except Exception:
                # 心跳失败通常意味着连接已断开
                # 下一次正常的业务请求或下一次心跳会通过 _execute 触发重连
                pass

    async def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        """执行命令；断线时指数退避重试。"""
        if self._limiter is not None:
            await self._limiter.acquire()
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError as first_exc:
                if not self._auto_reconnect:
                    raise
                last_exc: TdxConnectionError = first_exc
                for delay in self._retry_delays:
                    await asyncio.sleep(delay)
                    await self._conn.close()
                    self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
                    await self._conn.connect()
                    try:
                        return await self._conn.execute(cmd)
                    except TdxConnectionError as e:
                        last_exc = e
                raise last_exc

    async def _switch_host(self, host: str) -> None:
        """将底层连接切换到指定主机，并持久化为最佳主机。"""
        await self._conn.close()
        self._host = host
        self._conn = AsyncTdxConnection(host, self._port, self._timeout)
        await self._conn.connect()
        save_best_host(host)

    async def _execute_std(self, cmd: "BaseCommand[_T]", *, require_nonempty: bool = False) -> _T:
        """执行标准协议数据命令，自动避开不支持该命令的服务器。

        ``TdxClient._execute_std`` 的 asyncio 对应实现。
        """
        empty_result: Any = None
        last_exc: TdxDecodeError | None
        try:
            result = await self._execute(cmd)
            if result or not require_nonempty:
                return result
            empty_result = result
            last_exc = None
        except TdxDecodeError as exc:
            empty_result = None
            last_exc = exc

        for host in get_full_featured_hosts():
            if host == self._host:
                continue
            conn = AsyncTdxConnection(host, self._port, self._timeout)
            try:
                await conn.connect()
                result = await conn.execute(cmd)
            except Exception:
                continue
            finally:
                await conn.close()
            if result or not require_nonempty:
                await self._switch_host(host)
                return result
            empty_result = result
            last_exc = None

        if last_exc is not None:
            raise last_exc
        return cast("_T", empty_result)

    async def get_security_count(self, market: Market) -> int:
        return await self._execute(GetSecurityCountCmd(market))

    async def get_security_list(self, market: Market, start: int) -> pd.DataFrame:
        return _to_df(await self._execute(GetSecurityListCmd(market, start)))

    async def get_security_list_all(self, pages: int | str = "all") -> pd.DataFrame:
        """获取沪深 A 股完整证券列表，并自动挂载行业信息。

        Args:
            pages: 拉取页数。每个市场每页 1000 条。
                   "all" 拉取全部（默认，结果会缓存到本地文件）。
                   整数 N 表示每个市场只拉前 N 页，不缓存。

        注意：
            `Market.BJ` 的证券列表请求长期存在服务器超时问题，当前版本暂不纳入此方法。
        """
        log = logging.getLogger(__name__)

        if pages == "all":
            cached = _load_cache()
            if cached is not None:
                log.info("从缓存加载沪深 A 股列表，共 %d 只", len(cached))
                return _to_df(cached)

        def _max_start(count: int) -> int:
            if pages == "all":
                return count
            return min(count, int(pages) * 1000)

        industry_map: dict[str, tuple[str, str]] = {}
        try:
            cfg_data = await self.get_report_file("tdxhy.cfg")
            if cfg_data:
                industry_map = parse_tdxhy_cfg(cfg_data)
                log.info("行业配置已加载，共 %d 条映射", len(industry_map))
        except Exception:
            log.warning("无法获取 tdxhy.cfg，行业字段将为空")

        all_stocks: list[SecurityInfo] = []
        for market in [Market.SH, Market.SZ]:
            count = await self.get_security_count(market)
            limit = _max_start(count)
            total_pages = (limit + 999) // 1000
            for page_idx, start in enumerate(range(0, limit, 1000)):
                try:
                    stocks = await self._execute(GetSecurityListCmd(market, start))
                except Exception:
                    log.warning(
                        "%s 第 %d/%d 页获取失败，跳过", market.name, page_idx + 1, total_pages
                    )
                    continue
                log.info(
                    "%s 第 %d/%d 页: %d 条", market.name, page_idx + 1, total_pages, len(stocks)
                )
                for s in stocks:
                    is_a_share = (market == Market.SH and s.code.startswith(("60", "68"))) or (
                        market == Market.SZ and s.code.startswith(("00", "30"))
                    )
                    if is_a_share:
                        if s.code in industry_map:
                            s.industry_tdx, s.industry_sw = industry_map[s.code]
                        all_stocks.append(s)

        log.info("沪深 A 股总数: %d", len(all_stocks))
        if pages == "all":
            _save_cache(all_stocks)
        return _to_df(all_stocks)

    async def get_security_quotes(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        return _to_df(await self._execute_std(GetSecurityQuotesCmd(stocks), require_nonempty=True))

    async def get_price_limits(
        self, market: Market, code: str, name: str, pre_close: float
    ) -> tuple[float | None, float | None]:
        """按当前交易状态计算涨跌停价。"""
        listed_days: int | None = None
        no_limit_window_days = get_no_limit_window_days(market, code, name)
        if no_limit_window_days > 0:
            try:
                bars = await self._execute(
                    GetSecurityBarsCmd(market, code, KlineCategory.DAY, 0, no_limit_window_days + 1)
                )
                listed_days = len(bars)
            except Exception:
                listed_days = None

        return compute_price_limits(
            market,
            code,
            name,
            pre_close,
            listed_days=listed_days,
        )

    async def get_security_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        df = _to_df(
            await self._execute_std(
                GetSecurityBarsCmd(market, code, category, start, count), require_nonempty=True
            )
        )
        return _merge_bar_datetime(df, category in _DAILY_PLUS)

    async def get_index_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        df = _to_df(
            await self._execute_std(
                GetIndexBarsCmd(market, code, category, start, count), require_nonempty=True
            )
        )
        return _merge_bar_datetime(df, category in _DAILY_PLUS)

    async def get_security_features(self, start: int = 0, count: int = 2000) -> pd.DataFrame:
        """证券扩展特征（0x0452）异步版。"""
        return _to_df(
            await self._execute_std(GetSecurityFeatureCmd(start, count), require_nonempty=True)
        )

    async def get_quotes_encrypt(self, stocks: list[tuple[Market, str]]) -> pd.DataFrame:
        """加密批量行情（0x0547）异步版。"""
        return _to_df(await self._execute_std(GetQuotesEncryptCmd(stocks), require_nonempty=True))

    async def get_index_momentum(self, market: Market, code: str) -> pd.DataFrame:
        """指数动量（0x051c）异步版。"""
        values = await self._execute_std(GetIndexMomentumCmd(market, code), require_nonempty=True)
        return pd.DataFrame({"momentum": values})

    async def get_index_info(self, market: Market, code: str) -> IndexInfo:
        """指数概况（0x051d）异步版。"""
        return await self._execute_std(GetIndexInfoCmd(market, code))

    async def get_top_board(self, size: int = 20, category: int = 0) -> pd.DataFrame:
        """排行榜（0x053f）异步版。"""
        items = await self._execute_std(GetTopBoardCmd(category, size), require_nonempty=True)
        return _to_df(items)

    async def get_volume_profile(self, market: Market, code: str) -> VolumeProfile:
        """个股成交分布（0x051a）异步版。"""
        return await self._execute_std(GetVolumeProfileCmd(market, code))

    async def get_bars(
        self,
        market: Market,
        code: str,
        category: KlineCategory,
        start: int,
        count: int = 800,
    ) -> pd.DataFrame:
        """按市场与代码自动路由股票或指数 K 线。"""
        if _looks_like_index(market, code):
            return await self.get_index_bars(market, code, category, start, count)
        return await self.get_security_bars(market, code, category, start, count)

    async def get_bars_range(
        self,
        market: Market,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
        count: int = 800,
    ) -> pd.DataFrame:
        """分页获取日期闭区间 [start_date, end_date] 内的 K 线（升序、去重）。"""
        _validate_yyyymmdd(start_date, "start_date")
        _validate_yyyymmdd(end_date, "end_date")
        if start_date > end_date:
            raise ValueError("start_date 不能晚于 end_date")

        frames: list[pd.DataFrame] = []
        page_start = 0
        empty = pd.DataFrame()
        for _ in range(256):
            page = await self.get_bars(market, code, category, page_start, count)
            if page.empty:
                break
            col = _bar_date_column(page)
            days = pd.to_datetime(page[col]).dt.strftime("%Y%m%d").astype(int)
            mask = (days >= start_date) & (days <= end_date)
            if mask.any():
                frames.append(page.loc[mask])
            if int(days.min()) <= start_date or len(page) < count:
                break
            page_start += len(page)
            empty = page.iloc[0:0]

        if not frames:
            return empty
        result = pd.concat(frames, ignore_index=True)
        col = _bar_date_column(result)
        result = result.drop_duplicates(subset=[col]).sort_values(col).reset_index(drop=True)
        return result

    async def get_k_data(
        self,
        code: str,
        start_date: int,
        end_date: int,
        category: KlineCategory = KlineCategory.DAY,
    ) -> pd.DataFrame:
        """便捷获取某代码日期区间内的 K 线（自动推断市场，默认日线）。"""
        return await self.get_bars_range(_infer_market(code), code, start_date, end_date, category)

    async def get_trading_calendar(
        self,
        start_date: int = 19900101,
        end_date: int | None = None,
        *,
        market: Market = Market.SH,
        code: str = "000001",
        category: KlineCategory = KlineCategory.DAY,
    ) -> TradingCalendar:
        """由指数日线构建交易日历（默认上证指数）。"""
        if end_date is None:
            end_date = _today_in_shanghai()
        bars = await self.get_bars_range(market, code, start_date, end_date, category)
        return TradingCalendar.from_bars(bars)

    async def get_trading_days(
        self,
        start_date: int = 19900101,
        end_date: int | None = None,
        *,
        market: Market = Market.SH,
        code: str = "000001",
        category: KlineCategory = KlineCategory.DAY,
    ) -> list[date]:
        """返回 [start_date, end_date] 内的交易日（升序）。"""
        cal = await self.get_trading_calendar(
            start_date, end_date, market=market, code=code, category=category
        )
        return cal.days

    async def get_minute_time_data(self, market: Market, code: str) -> pd.DataFrame:
        today = _today_in_shanghai()
        bars = await self._execute(GetHistoryMinuteTimeDataCmd(market, code, today))
        return _add_minute_datetime(_to_df(bars), today)

    async def get_history_minute_time_data(
        self, market: Market, code: str, date: int
    ) -> pd.DataFrame:
        bars = await self._execute(GetHistoryMinuteTimeDataCmd(market, code, date))
        return _add_minute_datetime(_to_df(bars), date)

    async def get_recent_minute_time_data(
        self, market: Market, code: str, days: int = 5
    ) -> pd.DataFrame:
        """获取最近 N 个交易日的分时数据（异步版，逐日拉取 0x0fb4）。"""
        daily = await self.get_bars(market, code, KlineCategory.DAY, 0, days)
        if daily.empty:
            return pd.DataFrame()
        dates = sorted(int(pd.Timestamp(d).strftime("%Y%m%d")) for d in daily["date"])
        frames = [await self.get_history_minute_time_data(market, code, d) for d in dates]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    async def get_minute_aux(
        self, market: Market, code: str, kind: str | int = "buy_sell_strength"
    ) -> pd.DataFrame:
        """获取分时副图（0x051b），240 点（异步版）。"""
        selector = resolve_selector(kind)
        points = await self._execute_std(
            GetMinuteAuxCmd(market, code, selector), require_nonempty=True
        )
        volume_compare = selector == resolve_selector("volume_comparison")
        rows = [
            (
                {"index": p.index, "series_a": p.series_a, "series_b": p.series_b}
                if volume_compare
                else {"index": p.index, "buy": p.buy, "sell": p.sell}
            )
            for p in points
        ]
        return _add_minute_aux_time(pd.DataFrame(rows))

    async def get_sparkline(
        self, market: Market, code: str, selector: int = 1, window: int = 20
    ) -> pd.DataFrame:
        """小走势图（0x0fd1）异步版（该命令每连接仅响应一次，调用前重建连接）。"""
        await self._conn.close()
        self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
        await self._conn.connect()
        series = await self._execute_std(
            GetSparklineCmd(market, code, selector, window), require_nonempty=True
        )
        df = pd.DataFrame({"price": series.prices})
        df.attrs["base_price"] = series.base_price
        return df

    async def get_transaction_data(
        self, market: Market, code: str, start: int, count: int = 800
    ) -> pd.DataFrame:
        df = _to_df(
            await self._execute_std(
                GetTransactionDataCmd(market, code, start, count), require_nonempty=True
            )
        )
        return _merge_txn_datetime(df, _today_in_shanghai())

    async def get_history_transaction_data(
        self, market: Market, code: str, date: int, start: int, count: int = 800
    ) -> pd.DataFrame:
        df = _to_df(
            await self._execute_std(
                GetHistoryTransactionDataCmd(market, code, date, start, count),
                require_nonempty=True,
            )
        )
        return _merge_txn_datetime(df, date)

    async def get_history_transaction_all(
        self, market: Market, code: str, date: int, count: int = 800
    ) -> pd.DataFrame:
        out = await _paginate_async(
            lambda s, c: self.get_history_transaction_data(market, code, date, s, c), count
        )
        if out.empty:
            return out
        return out.sort_values("datetime").reset_index(drop=True)

    async def get_security_features_all(self, count: int = 2000) -> pd.DataFrame:
        """获取全部证券扩展特征（0x0452），自动分页。"""
        return await _paginate_async(lambda s, c: self.get_security_features(s, c), count)

    async def get_xdxr_info(self, market: Market, code: str) -> pd.DataFrame:
        return _to_df(await self._execute(GetXdxrInfoCmd(market, code)))

    async def get_finance_info(self, market: Market, code: str) -> pd.DataFrame:
        return _to_df(await self._execute(GetFinanceInfoCmd(market, code)))

    async def get_company_info_category(self, market: Market, code: str) -> pd.DataFrame:
        return _to_df(await self._execute(GetCompanyInfoCategoryCmd(market, code)))

    async def get_company_info_content(
        self, market: Market, code: str, filename: str, offset: int, length: int
    ) -> str:
        return await self._execute(GetCompanyInfoContentCmd(market, code, filename, offset, length))

    async def get_block_info(self, filename: str) -> pd.DataFrame:
        """获取并解析板块文件（行业、概念、风格等）。"""
        size, _hash = await self._execute(GetBlockInfoMetaCmd(filename))
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while pos < size:
            chunk = await self._execute(GetBlockInfoCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
        return _to_df(parse_block_dat(bytes(full_data), filename))

    async def get_report_file(self, filename: str) -> bytes:
        """从服务器拉取大文件。"""
        full_data = bytearray()
        pos = 0
        chunk_size = 30000
        while True:
            chunk = await self._execute(GetReportFileCmd(filename, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            if len(chunk) < chunk_size:
                break
        return bytes(full_data)

    # ------------------------------------------------------------------ #
    # 配置类加工数据（zhb.zip / tdxhy.cfg）
    # ------------------------------------------------------------------ #

    async def get_zhb_files(self) -> dict[str, bytes]:
        """下载并解压 zhb.zip，返回 {文件名: 原始字节}（结果缓存于实例）。"""
        if self._zhb_cache is not None:
            return self._zhb_cache
        self._zhb_cache = unzip_zhb(await self.get_report_file("zhb.zip"))
        return self._zhb_cache

    async def get_tdx_stat(self) -> pd.DataFrame:
        """个股综合统计（tdxstat.cfg）。"""
        return _to_df(parse_tdxstat((await self.get_zhb_files()).get("tdxstat.cfg", b"")))

    async def get_tdx_stat2(self) -> pd.DataFrame:
        """个股资金流向 + 板块归属（tdxstat2.cfg）。"""
        return _to_df(parse_tdxstat2((await self.get_zhb_files()).get("tdxstat2.cfg", b"")))

    async def get_xgsg(self) -> pd.DataFrame:
        """新股申购（xgsg.cfg）。"""
        return _to_df(parse_xgsg((await self.get_zhb_files()).get("xgsg.cfg", b"")))

    async def get_spblock(self, fill_index: bool = True) -> list[SpBlock]:
        """专业板块成分（spblock.dat）。"""
        files = await self.get_zhb_files()
        blocks = parse_spblock(files.get("spblock.dat", b""))
        if fill_index and blocks:
            fill_block_index_with_alias(
                blocks,
                parse_tdxzs(files.get("tdxzs.cfg", b"")),
                parse_tdxbk(files.get("tdxbk.cfg", b"")),
            )
        return blocks

    async def get_tdx_zs(self) -> pd.DataFrame:
        """板块指数配置（tdxzs.cfg）。"""
        return _to_df(parse_tdxzs((await self.get_zhb_files()).get("tdxzs.cfg", b"")))

    async def get_tdx_bk(self) -> pd.DataFrame:
        """板块简称↔全称（tdxbk.cfg）。"""
        return _to_df(parse_tdxbk((await self.get_zhb_files()).get("tdxbk.cfg", b"")))

    async def get_tdx_hy(self) -> pd.DataFrame:
        """行业归属（tdxhy.cfg）。"""
        return _to_df(parse_tdxhy(await self.get_report_file("tdxhy.cfg")))

    @staticmethod
    async def _async_download_from_host(
        host: str, filename: str, port: int = 7709, timeout: float = 15.0
    ) -> bytes:
        """从指定服务器创建临时异步连接并下载文件。"""
        conn = AsyncTdxConnection(host, port, timeout)
        try:
            await conn.connect()
            full_data = bytearray()
            pos = 0
            chunk_size = 30000
            while True:
                chunk = await conn.execute(GetReportFileCmd(filename, pos, chunk_size))
                if not chunk:
                    break
                full_data.extend(chunk)
                pos += len(chunk)
                if len(chunk) < chunk_size:
                    break
            return bytes(full_data)
        finally:
            await conn.close()

    async def get_financial_file_list(self, host: str | None = None) -> pd.DataFrame:
        """获取可用的历史专业财报文件列表（异步）。"""
        if host is None:
            host = get_calc_hosts()[0]
        data = await self._async_download_from_host(host, "tdxfin/gpcw.txt")
        raw_list = parse_financial_file_list(data)
        return _to_df([FinancialFileInfo(filename=f, hash=h, filesize=s) for f, h, s in raw_list])

    async def get_financial_file(self, filename: str, host: str | None = None) -> bytes:
        """从计算服务器下载财报 zip 文件（异步）。"""
        if host is None:
            host = get_calc_hosts()[0]
        return await self._async_download_from_host(host, filename)

    async def get_financial_records(self, filename: str, host: str | None = None) -> pd.DataFrame:
        """下载财报 zip 并解析为记录列表（异步）。"""
        if host is None:
            host = get_calc_hosts()[0]
        import io
        import re
        import zipfile

        zip_data = await self.get_financial_file(filename, host)
        if not zip_data:
            return pd.DataFrame()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            dat_names = [n for n in zf.namelist() if n.endswith(".dat")]
            if not dat_names:
                return pd.DataFrame()
            dat_data = zf.read(dat_names[0])

        m = re.search(r"(\d{8})", filename)
        report_date = int(m.group(1)) if m else 0

        raw_records = parse_financial_dat(dat_data, report_date)
        records: list[FinancialRecord] = []
        for code, market_byte, rdate, fields in raw_records:
            market = Market.SH if market_byte == 1 else Market.SZ
            records.append(
                FinancialRecord(code=code, market=market, report_date=rdate, fields=fields)
            )
        return _to_df(records)

    async def get_market_stat(self) -> pd.DataFrame:
        """获取 A 股全市场涨跌统计概况（基于 880005 行情统计）。

        注意：
            `suspended_count` 是 `total - up - down - neutral` 的残差估算值，
            用于保证计数守恒，不应视为协议已明确验证的停牌字段。
        """
        # 通达信中 880005 是全市场行情统计，880001 是总市值指数，880006 是涨跌停统计
        quotes = await self._execute(
            GetSecurityQuotesCmd(
                [(Market.SH, "880005"), (Market.SH, "880001"), (Market.SH, "880006")]
            )
        )
        if not quotes:
            raise RuntimeError("无法获取市场统计数据")
        q = quotes[0]
        up = int(q.price)
        down = int(q.open)
        neutral = int(q.low)
        total = int(q.high)
        market_cap = quotes[1].price * 1e10 if len(quotes) > 1 else 0.0
        limit_down = int(quotes[2].open) if len(quotes) > 2 else 0
        limit_up = int(quotes[2].price) if len(quotes) > 2 else 0
        return _to_df(
            MarketStat(
                up_count=up,
                down_count=down,
                neutral_count=neutral,
                suspended_count=max(0, total - up - down - neutral),
                total_count=total,
                total_amount=q.amount,
                total_volume=q.vol,
                total_market_cap=market_cap,
                limit_up_count=limit_up,
                limit_down_count=limit_down,
            )
        )

    async def _collect_transaction_records(
        self,
        fetch_page: Callable[[int, int], Awaitable[list[TransactionRecord]]],
        page_size: int,
        max_start: int = 10000,
    ) -> list[TransactionRecord]:
        all_recs: list[TransactionRecord] = []
        seen_sig: set[tuple[int, int, float, int, int, int]] = set()
        seen_page_sigs: set[
            tuple[
                tuple[int, int, float, int, int, int],
                tuple[int, int, float, int, int, int],
            ]
        ] = set()
        start = 0

        while start < max_start:
            recs = await fetch_page(start, page_size)
            if not recs:
                break

            page_sig = _page_signature(recs)
            if page_sig in seen_page_sigs:
                break
            seen_page_sigs.add(page_sig)

            new_count = 0
            for record in recs:
                sig = _record_signature(record)
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    all_recs.append(record)
                    new_count += 1

            if new_count == 0:
                break

            start += len(recs)
            if len(recs) < 100:
                break

        return all_recs

    async def get_fund_flow(self, market: Market, code: str) -> pd.DataFrame:
        """获取个股当日资金流向分布（基于 L1 逐笔数据统计）。"""
        records = await self._collect_transaction_records(
            lambda start, page_size: self._execute(
                GetTransactionDataCmd(market, code, start, page_size)
            ),
            2000,
        )
        return _to_df(_classify_fund_flow(records))

    async def get_history_fund_flow(
        self, market: Market, code: str, start: int, count: int
    ) -> pd.DataFrame:
        """获取个股历史日线资金流向序列。

        优先走 Category 22 直连接口；若服务器返回空列表，则自动回退为
        "日 K 线取日期 + 历史逐笔成交重算资金流"的兼容实现。
        """
        try:
            direct = await self._execute(GetHistoryFundFlowCmd(market, code, start, count))
        except Exception:
            direct = []
        if direct:
            return _to_df(direct)

        bars = await self._execute(
            GetSecurityBarsCmd(market, code, KlineCategory.DAY, start, count)
        )
        results: list[HistoricalFundFlow] = []
        for bar in bars:
            date = _date_from_bar(bar)
            records = await self._collect_transaction_records(
                lambda page_start, page_size: self._execute(
                    GetHistoryTransactionDataCmd(market, code, date, page_start, page_size)
                ),
                800,
            )
            results.append(_historical_fund_flow_from_records(date, records))
        return _to_df(results)
