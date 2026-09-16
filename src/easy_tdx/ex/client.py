"""扩展行情高层 API：ExTdxClient（同步）和 AsyncExTdxClient（asyncio）。"""

import asyncio
from collections import OrderedDict
from types import TracebackType
from typing import TypeVar

from ..commands.base import BaseCommand
from ..config import get_best_ex_host, get_ex_hosts, save_best_ex_host
from ..exceptions import TdxConnectionError
from .commands.get_history_bars_range import GetExHistoryInstrumentBarsRangeCmd
from .commands.get_instrument_bars import GetExInstrumentBarsCmd
from .commands.get_instrument_count import GetExInstrumentCountCmd
from .commands.get_instrument_info import GetExInstrumentInfoCmd
from .commands.get_instrument_quote import GetExInstrumentQuoteCmd
from .commands.get_instrument_quote_list import GetExInstrumentQuoteListCmd
from .commands.get_markets import GetExMarketsCmd
from .commands.get_minute_time import (
    GetExHistoryMinuteTimeDataCmd,
    GetExMinuteTimeDataCmd,
)
from .commands.get_server_info import GetExServerInfoCmd
from .commands.get_transaction import (
    GetExHistoryTransactionDataCmd,
    GetExTransactionDataCmd,
)
from .models import (
    ExInstrumentBar,
    ExInstrumentInfo,
    ExInstrumentQuote,
    ExMarketInfo,
    ExMinuteBar,
    ExServerInfo,
    ExTransactionRecord,
)
from .transport.async_ import AsyncExTdxConnection
from .transport.sync import ExTdxConnection, ping_ex_all

_DEFAULT_EX_PORT = 7727
_T = TypeVar("_T")


# ============================================================
# 同步客户端
# ============================================================


class ExTdxClient:
    """同步扩展行情客户端（期货、港股、外股等，端口 7727）。

    使用示例::

        with ExTdxClient("61.152.107.141") as c:
            markets = c.get_markets()
            quote = c.get_instrument_quote(47, "IFL0")
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
    ) -> None:
        self._host = host if host is not None else get_best_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._conn = ExTdxConnection(self._host, port, timeout)

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
    ) -> "ExTdxClient":
        """测量所有扩展行情服务器延迟，选最低延迟建立连接。自动保存最佳主机。"""
        if hosts is None:
            hosts = get_ex_hosts()
        ranked = ping_ex_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_ex_host(best)
        return cls(best, port, timeout, auto_reconnect)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    def connect(self) -> None:
        self._conn.connect()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ExTdxClient":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        try:
            return self._conn.execute(cmd)
        except TdxConnectionError:
            if not self._auto_reconnect:
                raise
            self._conn.close()
            self._conn = ExTdxConnection(self._host, self._port, self._timeout)
            self._conn.connect()
            return self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    def get_markets(self) -> list[ExMarketInfo]:
        """获取扩展行情支持的市场列表。"""
        return self._execute(GetExMarketsCmd())

    def get_server_info(self) -> ExServerInfo:
        """获取扩展市场服务器信息（0x2455）。"""
        return self._execute(GetExServerInfoCmd())

    def get_instrument_count(self) -> int:
        """获取扩展行情商品总数。"""
        return self._execute(GetExInstrumentCountCmd())

    def get_instrument_info(self, start: int, count: int = 100) -> list[ExInstrumentInfo]:
        """获取商品信息列表（分页）。"""
        return self._execute(GetExInstrumentInfoCmd(start, count))

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    def get_instrument_quote(self, market: int, code: str) -> ExInstrumentQuote | None:
        """获取单个商品五档实时行情。"""
        return self._execute(GetExInstrumentQuoteCmd(market, code))

    def get_instrument_quote_list(
        self,
        market: int,
        category: int,
        start: int = 0,
        count: int = 80,
    ) -> list[OrderedDict[str, object]]:
        """按类别获取商品行情列表。"""
        return self._execute(GetExInstrumentQuoteListCmd(market, category, start, count))

    # ------------------------------------------------------------------ #
    # K线
    # ------------------------------------------------------------------ #

    def get_instrument_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int = 0,
        count: int = 700,
    ) -> list[ExInstrumentBar]:
        """获取K线数据。"""
        return self._execute(GetExInstrumentBarsCmd(category, market, code, start, count))

    def get_history_instrument_bars_range(
        self,
        market: int,
        code: str,
        start_date: int,
        end_date: int,
    ) -> list[ExInstrumentBar]:
        """按日期范围获取历史K线。"""
        return self._execute(GetExHistoryInstrumentBarsRangeCmd(market, code, start_date, end_date))

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    def get_minute_time_data(self, market: int, code: str) -> list[ExMinuteBar]:
        """获取当日分时行情数据。"""
        return self._execute(GetExMinuteTimeDataCmd(market, code))

    def get_history_minute_time_data(
        self,
        market: int,
        code: str,
        date: int,
    ) -> list[ExMinuteBar]:
        """获取历史某日分时行情数据（date: YYYYMMDD）。"""
        return self._execute(GetExHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    def get_transaction_data(
        self,
        market: int,
        code: str,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        """获取当日分笔成交数据。"""
        return self._execute(GetExTransactionDataCmd(market, code, start, count))

    def get_history_transaction_data(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        """获取历史某日分笔成交数据（date: YYYYMMDD）。"""
        return self._execute(GetExHistoryTransactionDataCmd(market, code, date, start, count))


# ============================================================
# 异步客户端
# ============================================================


class AsyncExTdxClient:
    """异步扩展行情客户端（asyncio，端口 7727）。

    使用示例::

        async with AsyncExTdxClient("61.152.107.141") as c:
            markets = await c.get_markets()
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> None:
        self._host = host if host is not None else get_best_ex_host()
        self._port = port
        self._timeout = timeout
        self._auto_reconnect = auto_reconnect
        self._heartbeat_interval = heartbeat_interval
        self._conn = AsyncExTdxConnection(self._host, port, timeout)
        self._execute_lock = asyncio.Lock()
        self._heartbeat_task: asyncio.Task[None] | None = None

    @classmethod
    def from_best_host(
        cls,
        hosts: list[str] | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 15.0,
        ping_timeout: float = 5.0,
        auto_reconnect: bool = True,
        heartbeat_interval: float = 60.0,
    ) -> "AsyncExTdxClient":
        if hosts is None:
            hosts = get_ex_hosts()
        ranked = ping_ex_all(hosts, port, ping_timeout)
        best = ranked[0][0] if ranked else hosts[0]
        save_best_ex_host(best)
        return cls(best, port, timeout, auto_reconnect, heartbeat_interval)

    @staticmethod
    def ping_all(
        hosts: list[str] | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = 5.0,
    ) -> list[tuple[str, float]]:
        return ping_ex_all(hosts, port, timeout)

    # ------------------------------------------------------------------ #
    # 连接管理
    # ------------------------------------------------------------------ #

    async def connect(self) -> None:
        await self._conn.connect()
        self._start_heartbeat()

    async def close(self) -> None:
        await self._stop_heartbeat()
        await self._conn.close()

    async def __aenter__(self) -> "AsyncExTdxClient":
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
                await self.get_instrument_count()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _execute(self, cmd: "BaseCommand[_T]") -> _T:
        async with self._execute_lock:
            try:
                return await self._conn.execute(cmd)
            except TdxConnectionError:
                if not self._auto_reconnect:
                    raise
                await self._conn.close()
                self._conn = AsyncExTdxConnection(self._host, self._port, self._timeout)
                await self._conn.connect()
                return await self._conn.execute(cmd)

    # ------------------------------------------------------------------ #
    # 市场信息
    # ------------------------------------------------------------------ #

    async def get_markets(self) -> list[ExMarketInfo]:
        return await self._execute(GetExMarketsCmd())

    async def get_server_info(self) -> ExServerInfo:
        """获取扩展市场服务器信息（0x2455）异步版。"""
        return await self._execute(GetExServerInfoCmd())

    async def get_instrument_count(self) -> int:
        return await self._execute(GetExInstrumentCountCmd())

    async def get_instrument_info(
        self,
        start: int,
        count: int = 100,
    ) -> list[ExInstrumentInfo]:
        return await self._execute(GetExInstrumentInfoCmd(start, count))

    # ------------------------------------------------------------------ #
    # 行情
    # ------------------------------------------------------------------ #

    async def get_instrument_quote(
        self,
        market: int,
        code: str,
    ) -> ExInstrumentQuote | None:
        return await self._execute(GetExInstrumentQuoteCmd(market, code))

    async def get_instrument_quote_list(
        self,
        market: int,
        category: int,
        start: int = 0,
        count: int = 80,
    ) -> list[OrderedDict[str, object]]:
        return await self._execute(GetExInstrumentQuoteListCmd(market, category, start, count))

    # ------------------------------------------------------------------ #
    # K线
    # ------------------------------------------------------------------ #

    async def get_instrument_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int = 0,
        count: int = 700,
    ) -> list[ExInstrumentBar]:
        return await self._execute(GetExInstrumentBarsCmd(category, market, code, start, count))

    async def get_history_instrument_bars_range(
        self,
        market: int,
        code: str,
        start_date: int,
        end_date: int,
    ) -> list[ExInstrumentBar]:
        return await self._execute(
            GetExHistoryInstrumentBarsRangeCmd(market, code, start_date, end_date)
        )

    # ------------------------------------------------------------------ #
    # 分时
    # ------------------------------------------------------------------ #

    async def get_minute_time_data(self, market: int, code: str) -> list[ExMinuteBar]:
        return await self._execute(GetExMinuteTimeDataCmd(market, code))

    async def get_history_minute_time_data(
        self,
        market: int,
        code: str,
        date: int,
    ) -> list[ExMinuteBar]:
        return await self._execute(GetExHistoryMinuteTimeDataCmd(market, code, date))

    # ------------------------------------------------------------------ #
    # 成交
    # ------------------------------------------------------------------ #

    async def get_transaction_data(
        self,
        market: int,
        code: str,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        return await self._execute(GetExTransactionDataCmd(market, code, start, count))

    async def get_history_transaction_data(
        self,
        market: int,
        code: str,
        date: int,
        start: int = 0,
        count: int = 1800,
    ) -> list[ExTransactionRecord]:
        return await self._execute(GetExHistoryTransactionDataCmd(market, code, date, start, count))
