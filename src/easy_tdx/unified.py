"""统一通达信客户端 -- 自动路由 A 股 / 扩展市场。"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pandas as pd

from .client import AsyncTdxClient, TdxClient
from .codec.bitmap import Fields
from .ex.mac_client import AsyncMacExClient, MacExClient
from .exceptions import TdxError
from .mac.client import AsyncMacClient, MacClient
from .mac.enums import (
    Adjust,
    BoardType,
    Category,
    FilterType,
    Period,
    SortOrder,
    SortType,
)
from .models.enums import Market


class UnifiedTdxClient:
    """统一通达信行情客户端。

    自动路由：A 股方法代理到 MacClient，扩展市场方法代理到 MacExClient。
    对**两种协议重叠**的方法（行情/逐笔），默认 **MAC 优先、标准协议兜底**，
    避免某台 MAC 主机异常导致整体不可用（`fallback_std=False` 可关闭）。

    用法::

        with UnifiedTdxClient() as client:
            df = client.get_stock_kline(0, "600000", Period.DAILY, count=10)
            df2 = client.goods_kline(ExMarket.US_STOCK, "TSLA", Period.DAILY, count=10)
    """

    def __init__(
        self,
        heartbeat_interval: float = 15.0,
        timeout: float = 15.0,
        fallback_std: bool = True,
        std_client: TdxClient | None = None,
    ) -> None:
        self._heartbeat_interval = heartbeat_interval
        self._timeout = timeout
        self._fallback_std = fallback_std
        self._mac: MacClient | None = None
        self._mac_ex: MacExClient | None = None
        self._std: TdxClient | None = std_client

    def connect(self) -> None:
        self._ensure_mac()

    def close(self) -> None:
        if self._mac is not None:
            self._mac.close()
            self._mac = None
        if self._mac_ex is not None:
            self._mac_ex.close()
            self._mac_ex = None
        if self._std is not None:
            self._std.close()
            self._std = None

    def disconnect(self) -> None:
        self.close()

    def __enter__(self) -> UnifiedTdxClient:
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
    # 内部路由
    # ------------------------------------------------------------------ #

    def _ensure_mac(self) -> MacClient:
        if self._mac is None:
            self._mac = MacClient.from_best_host(
                heartbeat_interval=self._heartbeat_interval,
                timeout=self._timeout,
            )
            self._mac.connect()
        return self._mac

    def _ensure_mac_ex(self) -> MacExClient:
        if self._mac_ex is None:
            self._mac_ex = MacExClient.from_best_host(timeout=self._timeout)
            self._mac_ex.connect()
        return self._mac_ex

    def _ensure_std(self) -> TdxClient:
        if self._std is None:
            self._std = TdxClient.from_best_host(timeout=self._timeout)
            self._std.connect()
        return self._std

    def _mac_then_std(self, mac_call: Any, std_call: Any) -> pd.DataFrame:
        """重叠能力：MAC 优先，异常或空结果时回退标准协议（`fallback_std=False` 可关闭）。"""
        try:
            df = mac_call()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except TdxError:
            if not self._fallback_std:
                raise
        if not self._fallback_std:
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        return std_call()

    @staticmethod
    def _market(market: int) -> Market:
        return Market(market)

    # ------------------------------------------------------------------ #
    # A 股方法 (proxy to MacClient)
    # ------------------------------------------------------------------ #

    def get_stock_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Fields | None = None,
    ) -> pd.DataFrame:
        """批量报价：MAC 优先，失败/空时回退标准协议（回退结果按标准协议字段）。"""
        std_stocks = [(self._market(m), code) for m, code in stocks]
        return self._mac_then_std(
            lambda: self._ensure_mac().get_stock_quotes(stocks, fields),
            lambda: self._ensure_std().get_security_quotes(std_stocks),
        )

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
        return self._ensure_mac().get_stock_quotes_list(
            category, start, count, sort_type, sort_order, exclude_flags, fields
        )

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
        return self._ensure_mac().get_stock_kline(market, code, period, start, count, times, adjust)

    def get_tick_chart(
        self,
        market: int,
        code: str,
        date: int | None = None,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_tick_chart(market, code, date)

    def get_tick_charts(
        self,
        market: int,
        code: str,
        date: int | None = None,
        days: int = 5,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_tick_charts(market, code, date, days)

    def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac().get_chart_sampling(market, code)

    def get_transactions(
        self,
        market: int,
        code: str,
        count: int = 2000,
        start: int = 0,
        date: int | None = None,
    ) -> pd.DataFrame:
        """逐笔成交：MAC 优先，失败/空时回退标准协议（当日 / 历史按 date 自动选）。"""
        mkt = self._market(market)

        def _std() -> pd.DataFrame:
            c = self._ensure_std()
            if date is None:
                return c.get_transaction_data(mkt, code, start, count)
            return c.get_history_transaction_data(mkt, code, date, start, count)

        return self._mac_then_std(
            lambda: self._ensure_mac().get_transactions(market, code, count, start, date),
            _std,
        )

    def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac().get_symbol_info(market, code)

    def get_board_list(
        self,
        board_type: BoardType = BoardType.ALL,
        count: int = 10000,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_board_list(board_type, count)

    def get_board_members(
        self,
        board_symbol: str,
        count: int = 100000,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        fields: Fields | None = None,
        exclude_flags: list[FilterType] | None = None,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_board_members(
            board_symbol, count, sort_type, sort_order, fields, exclude_flags
        )

    def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac().get_belong_board(market, code)

    def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac().get_capital_flow(market, code)

    def get_auction(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac().get_auction(market, code)

    def get_unusual(
        self,
        market: int,
        start: int = 0,
        count: int = 0,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_unusual(market, start, count)

    def get_server_info(self) -> pd.DataFrame:
        return self._ensure_mac().get_server_info()

    def get_kline_offset(
        self,
        offset: int = 0,
        count: int = 128000,
    ) -> pd.DataFrame:
        return self._ensure_mac().get_kline_offset(offset, count)

    def get_file_meta(self, filename: str) -> pd.DataFrame:
        return self._ensure_mac().get_file_meta(filename)

    def download_file_chunk(
        self,
        filename: str,
        index: int,
        offset: int,
        size: int,
    ) -> bytes:
        return self._ensure_mac().download_file_chunk(filename, index, offset, size)

    def download_file(
        self,
        filename: str,
        filesize: int = 0,
    ) -> bytearray:
        return self._ensure_mac().download_file(filename, filesize)

    def get_goods_list(
        self,
        market: int,
        start: int = 0,
        count: int = 600,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_list(market, start, count)

    # ------------------------------------------------------------------ #
    # 扩展市场方法 (proxy to MacExClient)
    # ------------------------------------------------------------------ #

    def goods_count(self, market: int) -> int:
        return self._ensure_mac_ex().goods_count(market)

    def goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_list(market, start, count)

    def goods_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Any = None,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_quotes(stocks, fields)

    def goods_quotes_list(
        self,
        market: int,
        start: int = 0,
        count: int = 100,
        sort_type: SortType = SortType.CODE,
        sort_order: SortOrder = SortOrder.NONE,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_quotes_list(market, start, count, sort_type, sort_order)

    def goods_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_kline(market, code, period, start, count, adjust)

    def goods_tick_chart(
        self,
        market: int,
        code: str,
        query_date: object = None,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_tick_chart(market, code, query_date)  # type: ignore[arg-type]

    def goods_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_chart_sampling(market, code)

    def goods_transaction(
        self,
        market: int,
        code: str,
        query_date: object = None,
        start: int = 0,
        count: int = 2000,
    ) -> pd.DataFrame:
        return self._ensure_mac_ex().goods_transaction(market, code, query_date, start, count)  # type: ignore[arg-type]


class AsyncUnifiedTdxClient:
    """异步统一通达信行情客户端。

    用法::

        async with AsyncUnifiedTdxClient() as client:
            df = await client.get_stock_kline(0, "600000", Period.DAILY, count=10)
            df2 = await client.goods_kline(ExMarket.US_STOCK, "TSLA", Period.DAILY, count=10)
    """

    def __init__(
        self,
        heartbeat_interval: float = 15.0,
        timeout: float = 15.0,
        fallback_std: bool = True,
        std_client: AsyncTdxClient | None = None,
    ) -> None:
        self._heartbeat_interval = heartbeat_interval
        self._timeout = timeout
        self._fallback_std = fallback_std
        self._mac: AsyncMacClient | None = None
        self._mac_ex: AsyncMacExClient | None = None
        self._std: AsyncTdxClient | None = std_client

    async def connect(self) -> None:
        await self._ensure_mac()

    async def close(self) -> None:
        if self._mac is not None:
            await self._mac.close()
            self._mac = None
        if self._mac_ex is not None:
            await self._mac_ex.close()
            self._mac_ex = None
        if self._std is not None:
            await self._std.close()
            self._std = None

    async def disconnect(self) -> None:
        await self.close()

    async def __aenter__(self) -> AsyncUnifiedTdxClient:
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
    # 内部路由
    # ------------------------------------------------------------------ #

    async def _ensure_mac(self) -> AsyncMacClient:
        if self._mac is None:
            self._mac = AsyncMacClient.from_best_host(
                heartbeat_interval=self._heartbeat_interval,
                timeout=self._timeout,
            )
            await self._mac.connect()
        return self._mac

    async def _ensure_mac_ex(self) -> AsyncMacExClient:
        if self._mac_ex is None:
            self._mac_ex = AsyncMacExClient.from_best_host(timeout=self._timeout)
            await self._mac_ex.connect()
        return self._mac_ex

    async def _ensure_std(self) -> AsyncTdxClient:
        if self._std is None:
            self._std = AsyncTdxClient.from_best_host(timeout=self._timeout)
            await self._std.connect()
        return self._std

    async def _mac_then_std(self, mac_call: Any, std_call: Any) -> pd.DataFrame:
        """重叠能力：MAC 优先，异常或空结果时回退标准协议。"""
        df: pd.DataFrame | None = None
        try:
            df = await mac_call()
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except TdxError:
            if not self._fallback_std:
                raise
        if not self._fallback_std:
            return df if isinstance(df, pd.DataFrame) else pd.DataFrame()
        return await std_call()

    # ------------------------------------------------------------------ #
    # A 股方法 (proxy to AsyncMacClient)
    # ------------------------------------------------------------------ #

    async def get_stock_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Fields | None = None,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        std_stocks = [(Market(m), code) for m, code in stocks]

        async def _std() -> pd.DataFrame:
            c = await self._ensure_std()
            return await c.get_security_quotes(std_stocks)

        return await self._mac_then_std(lambda: mac.get_stock_quotes(stocks, fields), _std)

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
        mac = await self._ensure_mac()
        return await mac.get_stock_quotes_list(
            category, start, count, sort_type, sort_order, exclude_flags, fields
        )

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
        mac = await self._ensure_mac()
        return await mac.get_stock_kline(market, code, period, start, count, times, adjust)

    async def get_tick_chart(
        self,
        market: int,
        code: str,
        date: int | None = None,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_tick_chart(market, code, date)

    async def get_tick_charts(
        self,
        market: int,
        code: str,
        date: int | None = None,
        days: int = 5,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_tick_charts(market, code, date, days)

    async def get_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_chart_sampling(market, code)

    async def get_transactions(
        self,
        market: int,
        code: str,
        count: int = 2000,
        start: int = 0,
        date: int | None = None,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        mkt = Market(market)

        async def _std() -> pd.DataFrame:
            c = await self._ensure_std()
            if date is None:
                return await c.get_transaction_data(mkt, code, start, count)
            return await c.get_history_transaction_data(mkt, code, date, start, count)

        return await self._mac_then_std(
            lambda: mac.get_transactions(market, code, count, start, date), _std
        )

    async def get_symbol_info(self, market: int, code: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_symbol_info(market, code)

    async def get_board_list(
        self,
        board_type: BoardType = BoardType.ALL,
        count: int = 10000,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_board_list(board_type, count)

    async def get_board_members(
        self,
        board_symbol: str,
        count: int = 100000,
        sort_type: SortType = SortType.CHANGE_PCT,
        sort_order: SortOrder = SortOrder.DESC,
        fields: Fields | None = None,
        exclude_flags: list[FilterType] | None = None,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_board_members(
            board_symbol, count, sort_type, sort_order, fields, exclude_flags
        )

    async def get_belong_board(self, market: int, code: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_belong_board(market, code)

    async def get_capital_flow(self, market: int, code: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_capital_flow(market, code)

    async def get_auction(self, market: int, code: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_auction(market, code)

    async def get_unusual(
        self,
        market: int,
        start: int = 0,
        count: int = 0,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_unusual(market, start, count)

    async def get_server_info(self) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_server_info()

    async def get_kline_offset(
        self,
        offset: int = 0,
        count: int = 128000,
    ) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_kline_offset(offset, count)

    async def get_file_meta(self, filename: str) -> pd.DataFrame:
        mac = await self._ensure_mac()
        return await mac.get_file_meta(filename)

    async def download_file_chunk(
        self,
        filename: str,
        index: int,
        offset: int,
        size: int,
    ) -> bytes:
        mac = await self._ensure_mac()
        return await mac.download_file_chunk(filename, index, offset, size)

    async def download_file(
        self,
        filename: str,
        filesize: int = 0,
    ) -> bytearray:
        mac = await self._ensure_mac()
        return await mac.download_file(filename, filesize)

    async def get_goods_list(
        self,
        market: int,
        start: int = 0,
        count: int = 600,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_list(market, start, count)

    # ------------------------------------------------------------------ #
    # 扩展市场方法 (proxy to AsyncMacExClient)
    # ------------------------------------------------------------------ #

    async def goods_count(self, market: int) -> int:
        ex = await self._ensure_mac_ex()
        return await ex.goods_count(market)

    async def goods_list(self, market: int, start: int = 0, count: int = 600) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_list(market, start, count)

    async def goods_quotes(
        self,
        stocks: list[tuple[int, str]],
        fields: Any = None,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_quotes(stocks, fields)

    async def goods_quotes_list(
        self,
        market: int,
        start: int = 0,
        count: int = 100,
        sort_type: SortType = SortType.CODE,
        sort_order: SortOrder = SortOrder.NONE,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_quotes_list(market, start, count, sort_type, sort_order)

    async def goods_kline(
        self,
        market: int,
        code: str,
        period: Period = Period.DAILY,
        start: int = 0,
        count: int = 800,
        adjust: Adjust = Adjust.NONE,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_kline(market, code, period, start, count, adjust)

    async def goods_tick_chart(
        self,
        market: int,
        code: str,
        query_date: object = None,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_tick_chart(market, code, query_date)  # type: ignore[arg-type]

    async def goods_chart_sampling(self, market: int, code: str) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_chart_sampling(market, code)

    async def goods_transaction(
        self,
        market: int,
        code: str,
        query_date: object = None,
        start: int = 0,
        count: int = 2000,
    ) -> pd.DataFrame:
        ex = await self._ensure_mac_ex()
        return await ex.goods_transaction(market, code, query_date, start, count)  # type: ignore[arg-type]
