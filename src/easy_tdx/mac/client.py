"""MAC 协议高层 API：MacClient（同步）和 AsyncMacClient（asyncio）。"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar

import pandas as pd

from .._df import _to_df
from ..codec.bitmap import Fields, PresetField
from ..commands.base import BaseCommand
from ..config import get_best_host, get_mac_hosts, get_port, get_timeout, save_best_host
from ..exceptions import TdxConnectionError
from ..transport.async_ import AsyncTdxConnection
from ..transport.sync import TdxConnection, ping_mac_all

if TYPE_CHECKING:
    from ..ex.mac_client import AsyncMacExClient, MacExClient

from .commands import (
    BoardListCmd,
    BoardMembersQuotesCmd,
    KlineOffsetCmd,
    ServerInfoCmd,
    SymbolAuctionCmd,
    SymbolBarCmd,
    SymbolBelongBoardCmd,
    SymbolCapitalFlowCmd,
    SymbolInfoCmd,
    SymbolQuotesCmd,
    SymbolTickChartCmd,
    SymbolTransactionCmd,
    TickChartsCmd,
    UnusualCmd,
)
from .commands.file_query import FileDownloadCmd, FileListCmd
from .enums import Adjust, BoardType, Category, FilterType, Period, SortOrder, SortType
from .models import (
    MacBar,
    MacMultiTickChart,
    MacQuoteField,
    MacTickChart,
)

_RETRY_DELAYS = (0.1, 0.5, 1.0, 2.0)
_KLINE_PAGE_SIZE = 700
_BOARD_MEMBERS_PAGE_SIZE = 80


def _convert_board_code(board_symbol: str) -> int:
    """将用户可见的板块代码转换为服务器协议代码。

    转换规则（来自 opentdx exchange_board_code）：
      US0401   → 30401   (30000 + N)
      HK0283   → 20283   (20000 + N)
      000686   → 31686   (31000 + N)
      399372   → 30372   (N - 399000 + 30000)
      899050   → 32050   (N - 899000 + 32000)
      880686   → 20686   (N - 880000 + 20000)
      其他      → int(N)
    """
    s = board_symbol.strip()
    if s.startswith("US"):
        return 30000 + int(s[2:])
    if s.startswith("HK"):
        return 20000 + int(s[2:])
    if len(s) == 6:
        if s.startswith("88"):
            return int(s) - 880000 + 20000
        if s.startswith("399"):
            return int(s) - 399000 + 30000
        if s.startswith("899"):
            return int(s) - 899000 + 32000
        if s.startswith("000"):
            return 31000 + int(s)
    return int(s)


_TRANSACTION_PAGE_SIZE = 1000

_T = TypeVar("_T")


def _flatten_quote_fields(quotes: list[MacQuoteField]) -> list[dict[str, Any]]:
    """将 MacQuoteField 展平为 DataFrame 友好的 dict 列表。"""
    rows: list[dict[str, Any]] = []
    for q in quotes:
        d: dict[str, Any] = {"market": q.market, "code": q.code, "name": q.name}
        d.update(q.fields)
        rows.append(d)
    return rows


def _quotes_to_df(quotes: list[MacQuoteField]) -> pd.DataFrame:
    return pd.DataFrame(_flatten_quote_fields(quotes))


def _flatten_tick_chart(chart: MacTickChart) -> list[dict[str, Any]]:
    """将 MacTickChart 的 ticks 展平为 DataFrame 行。"""
    rows: list[dict[str, Any]] = []
    for tick in chart.charts:
        rows.append(asdict(tick))
    return rows


def _flatten_multi_tick_chart(chart: MacMultiTickChart) -> list[dict[str, Any]]:
    """将 MacMultiTickChart 的所有天的 ticks 展平为 DataFrame 行。"""
    rows: list[dict[str, Any]] = []
    for day in chart.charts:
        for tick in day.ticks:
            d = asdict(tick)
            d["date"] = day.date
            d["pre_close"] = day.pre_close
            rows.append(d)
    return rows


# ============================================================
# 同步客户端
# ============================================================


class MacClient:
    """同步 MAC 协议客户端，支持 IP 优选与断线自动重连。

    使用示例::

        with MacClient("121.36.248.138") as c:
            df = c.get_stock_kline(0, "600000", Period.DAILY, count=100)

        # 自动选延迟最低的 MAC 服务器
        with MacClient.from_best_host() as c:
            df = c.get_board_list()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 15.0,
    ) -> None:
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = TdxConnection(self._host, self._port, self._timeout)
        self._mac_ex: MacExClient | None = None

    # ------------------------------------------------------------------ #
    # 工厂方法
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
    ) -> MacClient:
        """测量所有 MAC 服务器延迟，选最低延迟的建立客户端。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_mac_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台 MAC 服务器延迟，返回按延迟排序的 (host, seconds) 列表。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        return ping_mac_all(hosts, port, timeout)

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
        ex = self._mac_ex
        if ex is not None:
            ex.close()
            self._mac_ex = None

    def disconnect(self) -> None:
        """Alias for close()."""
        self.close()

    def ensure_connected(self) -> None:
        """验证连接存活，断线则自动重建。"""
        try:
            self._execute(KlineOffsetCmd(0, 1))
        except TdxConnectionError:
            self._conn.stop_heartbeat()
            self._conn.close()
            self._conn = TdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            if self._heartbeat_interval > 0:
                self._conn.start_heartbeat(self._heartbeat_interval)

    def __enter__(self) -> MacClient:
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

    def _execute(self, cmd: BaseCommand[_T]) -> _T:
        """执行命令；断线时指数退避重试。"""
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            last_exc: TdxConnectionError | None = None
            for delay in _RETRY_DELAYS:
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
            raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # 报价
    # ------------------------------------------------------------------ #

    def get_stock_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: object = None,
    ) -> pd.DataFrame:
        """批量获取自定义字段报价（最多80只/次）。

        Args:
            stocks: [(market, code), ...] 列表。
            fields: 字段选择，默认 PresetField.COMMON。
        """
        quotes = self._execute(SymbolQuotesCmd(stocks, fields))  # type: ignore[arg-type]
        return _quotes_to_df(quotes)

    def get_stock_quotes_list(
        self,
        category: Category,
        start: int = 0,
        count: int = 80,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        exclude_flags: list[FilterType] | None = None,
        fields: Fields | None = None,
    ) -> pd.DataFrame:
        """获取市场分类报价列表（自动分页）。

        Args:
            category: 市场分类（如 Category.A, Category.SH, Category.KCB 等）。
            start: 起始偏移。
            count: 请求总数。
            sort_type: 排序字段。
            sort_order: 排序方向。
            exclude_flags: 过滤标志列表。
            fields: 请求字段集合，默认 PresetField.BASIC + PresetField.VOLUME。
        """
        if fields is None:
            fields = PresetField.BASIC + PresetField.VOLUME
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        page_size = min(count, _BOARD_MEMBERS_PAGE_SIZE)
        offset = start

        while fetched < count:
            batch = self._execute(
                BoardMembersQuotesCmd(
                    board_code=int(category),
                    sort_type=sort_type,
                    start=offset,
                    page_size=page_size,
                    sort_order=sort_order,
                    fields=fields,
                    exclude_flags=exclude_flags,
                )
            )
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    # ------------------------------------------------------------------ #
    # K 线（支持复权）
    # ------------------------------------------------------------------ #

    def get_stock_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        times: int = 1,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
        """获取 K 线数据（自动分页，每页最多 700 条）。

        Args:
            market: 市场代码。
            code: 股票代码。
            period: K 线周期。
            start: 起始偏移（0 = 最新）。
            count: 总请求条数。
            times: 周期倍数（Period.MINS/DAYS 时有效）。
            adjust: 复权方式。
        """
        all_bars: list[MacBar] = []
        fetched = 0
        offset = start

        while fetched < count:
            page_size = min(count - fetched, _KLINE_PAGE_SIZE)
            bars = self._execute(
                SymbolBarCmd(
                    market=market,
                    code=code,
                    period=period,
                    times=times,
                    start=offset,
                    count=page_size,
                    fq=adjust,
                )
            )
            if not bars:
                break
            all_bars = bars + all_bars
            fetched += len(bars)
            offset += len(bars)
            if len(bars) < page_size:
                break

        return _to_df(all_bars)

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_tick_chart(
        self,
        market: int,
        code: str,
        date: int | None = None,
    ) -> pd.DataFrame:
        """获取单日分时图。

        Args:
            market: 市场代码。
            code: 股票代码。
            date: 查询日期（YYYYMMDD），None 表示今天。
        """
        from datetime import date as date_cls

        query_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        chart = self._execute(SymbolTickChartCmd(market, code, query_date))
        return pd.DataFrame(_flatten_tick_chart(chart))

    def get_tick_charts(
        self,
        market: int,
        code: str,
        date: int | None = None,
        days: int = 5,
    ) -> pd.DataFrame:
        """获取多日分时图（最多 5 天）。

        Args:
            market: 市场代码。
            code: 股票代码。
            date: 起始日期（YYYYMMDD），None 表示从最新交易日开始。
            days: 天数。
        """
        from datetime import date as date_cls

        start_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        chart = self._execute(TickChartsCmd(market, code, start_date, days))
        return pd.DataFrame(_flatten_multi_tick_chart(chart))

    def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        """获取分时缩略采样价格点（240 个点）。

        A 股分时缩略采样复用 MAC 分时图命令（0x122D），返回当日每分钟
        一个价格点（共 240 点）。原 0x254D 缩略采样命令仅在扩展市场
        （端口 7727）有效，在 A 股端口（7709）不会响应，故此处改用 0x122D。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        chart = self._execute(SymbolTickChartCmd(market, code))
        return pd.DataFrame({"price": [tick.price for tick in chart.charts]})

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    def get_transactions(
        self,
        market: int,
        code: str,
        count: int = 2000,
        start: int = 0,
        date: int | None = None,
    ) -> pd.DataFrame:
        """获取逐笔成交数据（自动分页）。

        Args:
            market: 市场代码。
            code: 股票代码。
            count: 请求总数。
            start: 起始偏移。
            date: 查询日期（YYYYMMDD），None 表示今天。
        """
        from datetime import date as date_cls

        query_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        all_items = self._execute(
            SymbolTransactionCmd(
                market, code, query_date, start, min(count, _TRANSACTION_PAGE_SIZE)
            )
        )
        fetched = len(all_items)
        offset = start + fetched

        while fetched < count:
            page_size = min(count - fetched, _TRANSACTION_PAGE_SIZE)
            batch = self._execute(SymbolTransactionCmd(market, code, query_date, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    # ------------------------------------------------------------------ #
    # 个股信息
    # ------------------------------------------------------------------ #

    def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        """获取个股简要特征快照。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        info = self._execute(SymbolInfoCmd(market, code))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 板块
    # ------------------------------------------------------------------ #

    def get_board_list(
        self,
        board_type: BoardType = BoardType.ALL,
        count: int = 10000,
    ) -> pd.DataFrame:
        """获取板块列表（自动分页）。

        Args:
            board_type: 板块类型。
            count: 请求总数。
        """
        all_items = self._execute(BoardListCmd(board_type, 0, min(count, 150)))
        fetched = len(all_items)
        offset = fetched

        while fetched < count:
            page_size = min(count - fetched, 150)
            batch = self._execute(BoardListCmd(board_type, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    def get_board_members(
        self,
        board_symbol: str,
        count: int = 100000,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        fields: object = PresetField.COMMON,
        exclude_flags: list[FilterType] | None = None,
    ) -> pd.DataFrame:
        """获取板块成分股报价（自动分页）。

        Args:
            board_symbol: 板块代码（如 "881001"）。
            count: 请求总数。
            sort_type: 排序字段。
            sort_order: 排序方向。
            fields: 字段选择。
            exclude_flags: 过滤标志列表。
        """
        board_code = _convert_board_code(board_symbol)
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        offset = 0

        while fetched < count:
            page_size = min(count - fetched, _BOARD_MEMBERS_PAGE_SIZE)
            batch = self._execute(
                BoardMembersQuotesCmd(
                    board_code=board_code,
                    sort_type=sort_type,
                    start=offset,
                    page_size=page_size,
                    sort_order=sort_order,
                    fields=fields,  # type: ignore[arg-type]
                    exclude_flags=exclude_flags,
                )
            )
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        """获取个股所属板块列表。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        items = self._execute(SymbolBelongBoardCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 资金流向
    # ------------------------------------------------------------------ #

    def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        """获取个股资金流向。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        data = self._execute(SymbolCapitalFlowCmd(market, code))
        if data is None:
            return pd.DataFrame()
        return _to_df(data)

    # ------------------------------------------------------------------ #
    # 集合竞价
    # ------------------------------------------------------------------ #

    def get_auction(self, market: int, code: str) -> pd.DataFrame:
        """获取集合竞价数据。

        Args:
            market: 市场代码。
            code: 股票代码。
        """
        items = self._execute(SymbolAuctionCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 异动
    # ------------------------------------------------------------------ #

    def get_unusual(
        self,
        market: int,
        start: int = 0,
        count: int = 0,
    ) -> pd.DataFrame:
        """获取市场异动数据。

        Args:
            market: 市场代码。
            start: 起始偏移。
            count: 请求数量（0 表示使用默认值 600）。
        """
        items = self._execute(UnusualCmd(market, start, count or 600))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 服务器信息
    # ------------------------------------------------------------------ #

    def get_server_info(self) -> pd.DataFrame:
        """获取服务器交易时段信息。"""
        info = self._execute(ServerInfoCmd())
        return _to_df(info)

    def get_kline_offset(
        self,
        offset: int = 0,
        count: int = 128000,
    ) -> pd.DataFrame:
        """获取 K 线数据偏移信息。

        Args:
            offset: 偏移量。
            count: 请求数量。
        """
        info = self._execute(KlineOffsetCmd(offset, count))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 文件操作
    # ------------------------------------------------------------------ #

    def get_file_meta(self, filename: str) -> pd.DataFrame:
        """查询远程文件元信息。

        Args:
            filename: 远程文件名。
        """
        meta = self._execute(FileListCmd(filename))
        return _to_df(meta)

    def download_file_chunk(
        self,
        filename: str,
        index: int,
        offset: int,
        size: int,
    ) -> bytes:
        """下载远程文件的一个分片。

        Args:
            filename: 远程文件名。
            index: 分段序号（1-based）。
            offset: 字节偏移。
            size: 请求块大小。
        """
        return self._execute(FileDownloadCmd(filename, index, offset, size))

    def download_file(
        self,
        filename: str,
        filesize: int = 0,
    ) -> bytearray:
        """下载完整远程文件。

        Args:
            filename: 远程文件名。
            filesize: 预期文件大小（0 表示自动检测）。
        """
        if filesize <= 0:
            meta = self._execute(FileListCmd(filename))
            filesize = meta.size

        full_data = bytearray()
        chunk_size = 30000
        pos = 0
        idx = 1

        while pos < filesize:
            chunk = self._execute(FileDownloadCmd(filename, idx, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            idx += 1
            if len(chunk) < chunk_size:
                break

        return full_data

    # ------------------------------------------------------------------ #
    # 扩展市场
    # ------------------------------------------------------------------ #

    def get_goods_list(
        self,
        market: int,
        start: int = 0,
        count: int = 600,
    ) -> pd.DataFrame:
        """获取扩展市场（期货/期权/港股/美股等）商品列表。

        扩展市场数据在 **MAC-EX（7727）** 通道，本方法内部自动建立并复用一条
        MAC-EX 连接（首次调用会测速选路）。

        Args:
            market: 扩展市场代码（ExMarket 枚举值，如 ``ExMarket.HK_MAIN_BOARD``）。
            start: 市场内起始偏移。
            count: 请求数量。
        """
        return self._ensure_mac_ex().goods_list(market, start, count)

    def _ensure_mac_ex(self) -> MacExClient:
        ex = self._mac_ex
        if ex is None:
            from ..ex.mac_client import MacExClient

            ex = MacExClient.from_best_host(timeout=self._timeout)
            ex.connect()
            self._mac_ex = ex
        return ex


# ============================================================
# 异步客户端
# ============================================================


class AsyncMacClient:
    """异步 MAC 协议客户端（asyncio）。

    使用示例::

        async with AsyncMacClient("121.36.248.138") as c:
            df = await c.get_stock_kline(0, "600000", Period.DAILY, count=100)

    注意：
        单个 AsyncMacClient 仅维护一条 TCP 连接；并发调用会在连接内串行执行。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 15.0,
    ) -> None:
        self._host = host if host is not None else get_best_host()
        self._port = port if port is not None else get_port()
        self._timeout = timeout if timeout is not None else get_timeout()
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
        self._mac_ex: AsyncMacExClient | None = None
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ #
    # 工厂方法
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
    ) -> AsyncMacClient:
        """测量所有 MAC 服务器延迟，选最低延迟的建立客户端。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        if timeout is None:
            timeout = get_timeout()
        ranked = ping_mac_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int | None = None,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        """测量多台 MAC 服务器延迟。"""
        if hosts is None:
            hosts = get_mac_hosts()
        if port is None:
            port = get_port()
        return ping_mac_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
        await self._conn.close()
        ex = self._mac_ex
        if ex is not None:
            await ex.close()
            self._mac_ex = None

    async def disconnect(self) -> None:
        """Alias for close()."""
        await self.close()

    async def ensure_connected(self) -> None:
        """验证连接存活，断线则自动重建。"""
        try:
            await self._execute(KlineOffsetCmd(0, 1))
        except TdxConnectionError:
            await self._stop_heartbeat()
            await self._conn.close()
            self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
            await self._conn.connect()
            self._start_heartbeat()

    async def __aenter__(self) -> AsyncMacClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # ------------------------------------------------------------------ #
    # 心跳
    # ------------------------------------------------------------------ #

    def _start_heartbeat(self) -> None:
        if self._heartbeat_interval <= 0:
            return
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self._execute(KlineOffsetCmd(0, 1))
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 内部执行
    # ------------------------------------------------------------------ #

    async def _execute(self, cmd: BaseCommand[_T]) -> _T:
        """执行命令；断线时指数退避重试。"""
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                last_exc: TdxConnectionError | None = None
                for delay in _RETRY_DELAYS:
                    await asyncio.sleep(delay)
                    await self._conn.close()
                    self._conn = AsyncTdxConnection(self._host, self._port, self._timeout)
                    await self._conn.connect()
                    try:
                        return await self._conn.execute(cmd)
                    except TdxConnectionError as e:
                        last_exc = e
                raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------ #
    # 报价
    # ------------------------------------------------------------------ #

    async def get_stock_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: object = None,
    ) -> pd.DataFrame:
        quotes = await self._execute(SymbolQuotesCmd(stocks, fields))  # type: ignore[arg-type]
        return _quotes_to_df(quotes)

    async def get_stock_quotes_list(
        self,
        category: Category,
        start: int = 0,
        count: int = 80,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        exclude_flags: list[FilterType] | None = None,
        fields: Fields | None = None,
    ) -> pd.DataFrame:
        if fields is None:
            fields = PresetField.BASIC + PresetField.VOLUME
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        page_size = min(count, _BOARD_MEMBERS_PAGE_SIZE)
        offset = start

        while fetched < count:
            batch = await self._execute(
                BoardMembersQuotesCmd(
                    board_code=int(category),
                    sort_type=sort_type,
                    start=offset,
                    page_size=page_size,
                    sort_order=sort_order,
                    fields=fields,
                    exclude_flags=exclude_flags,
                )
            )
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    # ------------------------------------------------------------------ #
    # K 线
    # ------------------------------------------------------------------ #

    async def get_stock_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        times: int = 1,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
        all_bars: list[MacBar] = []
        fetched = 0
        offset = start

        while fetched < count:
            page_size = min(count - fetched, _KLINE_PAGE_SIZE)
            bars = await self._execute(
                SymbolBarCmd(
                    market=market,
                    code=code,
                    period=period,
                    times=times,
                    start=offset,
                    count=page_size,
                    fq=adjust,
                )
            )
            if not bars:
                break
            all_bars = bars + all_bars
            fetched += len(bars)
            offset += len(bars)
            if len(bars) < page_size:
                break

        return _to_df(all_bars)

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    async def get_tick_chart(
        self,
        market: int,
        code: str,
        date: int | None = None,
    ) -> pd.DataFrame:
        from datetime import date as date_cls

        query_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        chart = await self._execute(SymbolTickChartCmd(market, code, query_date))
        return pd.DataFrame(_flatten_tick_chart(chart))

    async def get_tick_charts(
        self,
        market: int,
        code: str,
        date: int | None = None,
        days: int = 5,
    ) -> pd.DataFrame:
        from datetime import date as date_cls

        start_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        chart = await self._execute(TickChartsCmd(market, code, start_date, days))
        return pd.DataFrame(_flatten_multi_tick_chart(chart))

    async def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        chart = await self._execute(SymbolTickChartCmd(market, code))
        return pd.DataFrame({"price": [tick.price for tick in chart.charts]})

    # ------------------------------------------------------------------ #
    # 逐笔成交
    # ------------------------------------------------------------------ #

    async def get_transactions(
        self,
        market: int,
        code: str,
        count: int = 2000,
        start: int = 0,
        date: int | None = None,
    ) -> pd.DataFrame:
        from datetime import date as date_cls

        query_date = (
            date_cls(date // 10000, (date % 10000) // 100, date % 100) if date is not None else None
        )
        all_items = await self._execute(
            SymbolTransactionCmd(
                market, code, query_date, start, min(count, _TRANSACTION_PAGE_SIZE)
            )
        )
        fetched = len(all_items)
        offset = start + fetched

        while fetched < count:
            page_size = min(count - fetched, _TRANSACTION_PAGE_SIZE)
            batch = await self._execute(
                SymbolTransactionCmd(market, code, query_date, offset, page_size)
            )
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    # ------------------------------------------------------------------ #
    # 个股信息
    # ------------------------------------------------------------------ #

    async def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        info = await self._execute(SymbolInfoCmd(market, code))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 板块
    # ------------------------------------------------------------------ #

    async def get_board_list(
        self,
        board_type: BoardType = BoardType.ALL,
        count: int = 10000,
    ) -> pd.DataFrame:
        all_items = await self._execute(BoardListCmd(board_type, 0, min(count, 150)))
        fetched = len(all_items)
        offset = fetched

        while fetched < count:
            page_size = min(count - fetched, 150)
            batch = await self._execute(BoardListCmd(board_type, offset, page_size))
            if not batch:
                break
            all_items.extend(batch)
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _to_df(all_items)

    async def get_board_members(
        self,
        board_symbol: str,
        count: int = 100000,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        fields: object = PresetField.COMMON,
        exclude_flags: list[FilterType] | None = None,
    ) -> pd.DataFrame:
        board_code = _convert_board_code(board_symbol)
        all_quotes: list[MacQuoteField] = []
        fetched = 0
        offset = 0

        while fetched < count:
            page_size = min(count - fetched, _BOARD_MEMBERS_PAGE_SIZE)
            batch = await self._execute(
                BoardMembersQuotesCmd(
                    board_code=board_code,
                    sort_type=sort_type,
                    start=offset,
                    page_size=page_size,
                    sort_order=sort_order,
                    fields=fields,  # type: ignore[arg-type]
                    exclude_flags=exclude_flags,
                )
            )
            if not batch:
                break
            all_quotes = batch + all_quotes
            fetched += len(batch)
            offset += len(batch)
            if len(batch) < page_size:
                break

        return _quotes_to_df(all_quotes)

    async def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        items = await self._execute(SymbolBelongBoardCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 资金流向
    # ------------------------------------------------------------------ #

    async def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        data = await self._execute(SymbolCapitalFlowCmd(market, code))
        if data is None:
            return pd.DataFrame()
        return _to_df(data)

    # ------------------------------------------------------------------ #
    # 集合竞价
    # ------------------------------------------------------------------ #

    async def get_auction(self, market: int, code: str) -> pd.DataFrame:
        items = await self._execute(SymbolAuctionCmd(market, code))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 异动
    # ------------------------------------------------------------------ #

    async def get_unusual(
        self,
        market: int,
        start: int = 0,
        count: int = 0,
    ) -> pd.DataFrame:
        items = await self._execute(UnusualCmd(market, start, count or 600))
        return _to_df(items)

    # ------------------------------------------------------------------ #
    # 服务器信息
    # ------------------------------------------------------------------ #

    async def get_server_info(self) -> pd.DataFrame:
        info = await self._execute(ServerInfoCmd())
        return _to_df(info)

    async def get_kline_offset(
        self,
        offset: int = 0,
        count: int = 128000,
    ) -> pd.DataFrame:
        info = await self._execute(KlineOffsetCmd(offset, count))
        return _to_df(info)

    # ------------------------------------------------------------------ #
    # 文件操作
    # ------------------------------------------------------------------ #

    async def get_file_meta(self, filename: str) -> pd.DataFrame:
        meta = await self._execute(FileListCmd(filename))
        return _to_df(meta)

    async def download_file_chunk(
        self,
        filename: str,
        index: int,
        offset: int,
        size: int,
    ) -> bytes:
        return await self._execute(FileDownloadCmd(filename, index, offset, size))

    async def download_file(
        self,
        filename: str,
        filesize: int = 0,
    ) -> bytearray:
        if filesize <= 0:
            meta = await self._execute(FileListCmd(filename))
            filesize = meta.size

        full_data = bytearray()
        chunk_size = 30000
        pos = 0
        idx = 1

        while pos < filesize:
            chunk = await self._execute(FileDownloadCmd(filename, idx, pos, chunk_size))
            if not chunk:
                break
            full_data.extend(chunk)
            pos += len(chunk)
            idx += 1
            if len(chunk) < chunk_size:
                break

        return full_data

    # ------------------------------------------------------------------ #
    # 扩展市场
    # ------------------------------------------------------------------ #

    async def get_goods_list(
        self,
        market: int,
        start: int = 0,
        count: int = 600,
    ) -> pd.DataFrame:
        """扩展市场商品列表（内部走 MAC-EX 7727 通道；异步版）。"""
        ex = self._mac_ex
        if ex is None:
            from ..ex.mac_client import AsyncMacExClient

            ex = AsyncMacExClient.from_best_host(timeout=self._timeout)
            await ex.connect()
            self._mac_ex = ex
        return await ex.goods_list(market, start, count)
