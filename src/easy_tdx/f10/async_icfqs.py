"""ICFQS 7615 异步客户端。

复用同步 :class:`IcfqsClient`（在线程池执行 HTTP），保持行为一致。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .icfqs import DEFAULT_ICFQS_ADDRESS, IcfqsClient
from .models import F10Response
from .transport import TqlexTransport


class AsyncIcfqsClient:
    """ICFQS 异步客户端。"""

    def __init__(
        self,
        address: str = DEFAULT_ICFQS_ADDRESS,
        timeout: float = 8.0,
        retries: int = 2,
        transport: TqlexTransport | None = None,
    ) -> None:
        self._sync = IcfqsClient(address, timeout=timeout, retries=retries, transport=transport)

    @property
    def base_url(self) -> str:
        return self._sync.base_url

    async def tql(self, entry: str, *params: Any) -> F10Response:
        return await asyncio.to_thread(self._sync.tql, entry, *params)

    async def post_json(self, entry: str, body: Any) -> F10Response:
        return await asyncio.to_thread(self._sync.post_json, entry, body)

    async def lhb_detail(self, symbol: str, start_date: str, end_date: str) -> F10Response:
        return await asyncio.to_thread(self._sync.lhb_detail, symbol, start_date, end_date)

    async def lhb_yyb_detail(self, yyb_name: str, start_date: str, end_date: str) -> F10Response:
        return await asyncio.to_thread(self._sync.lhb_yyb_detail, yyb_name, start_date, end_date)

    async def lhb_yz_detail(self, code: str, start_date: str, end_date: str) -> F10Response:
        return await asyncio.to_thread(self._sync.lhb_yz_detail, code, start_date, end_date)

    async def daily_review(self, review_type: str, date: str = "0", limit: int = 30) -> F10Response:
        return await asyncio.to_thread(self._sync.daily_review, review_type, date, limit)

    async def daily_review_latest_date(self) -> F10Response:
        return await asyncio.to_thread(self._sync.daily_review_latest_date)

    async def topic_list(self, category: str = "0", page: int = 1) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_list, category, page)

    async def topic_search(self, keyword: str) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_search, keyword)

    async def topics_new(self) -> F10Response:
        return await asyncio.to_thread(self._sync.topics_new)

    async def topics_hot(self) -> F10Response:
        return await asyncio.to_thread(self._sync.topics_hot)

    async def topics_events(self) -> F10Response:
        return await asyncio.to_thread(self._sync.topics_events)

    async def topics_top(self, top_n: int = 10) -> F10Response:
        return await asyncio.to_thread(self._sync.topics_top, top_n)

    async def topic_detail(self, code: str, setcode: str) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_detail, code, setcode)

    async def topic_kline(self, code: str, setcode: str) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_kline, code, setcode)

    async def topic_stocks(
        self, code: str, setcode: str, page: int = 1, size: int = 20
    ) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_stocks, code, setcode, page, size)

    async def topic_quotes(self, codes: list[tuple[str, str]]) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_quotes, codes)

    async def topic_rotation(
        self,
        data_num: int = 1,
        data_type: int = 1,
        data_date: int = 2,
        theme_type: str = "0",
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.topic_rotation, data_num, data_type, data_date, theme_type
        )

    async def quotes_batch(
        self, codes: list[tuple[str, str]], want_columns: list[str] | None = None
    ) -> F10Response:
        return await asyncio.to_thread(self._sync.quotes_batch, codes, want_columns)
