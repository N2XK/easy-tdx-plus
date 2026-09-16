"""7615 F10 / TQLEX 异步客户端。

底层复用同步 :class:`F10Client`（在线程池中执行 HTTP），
保证参数构造、缓存、解析逻辑与同步版完全一致。
"""

from __future__ import annotations

import asyncio
from typing import Any

from .client import F10Client
from .entries import DEFAULT_TQLEX_BASE_URL
from .models import F10Response
from .transport import TqlexTransport


class AsyncF10Client:
    """F10 异步客户端。"""

    def __init__(
        self,
        base_url: str = DEFAULT_TQLEX_BASE_URL,
        timeout: float = 8.0,
        retries: int = 2,
        transport: TqlexTransport | None = None,
        cache: bool = False,
        cache_ttl: float = 60.0,
        empty_retries: int = 2,
        empty_retry_delay: float = 0.5,
    ) -> None:
        self._sync = F10Client(
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            transport=transport,
            cache=cache,
            cache_ttl=cache_ttl,
            empty_retries=empty_retries,
            empty_retry_delay=empty_retry_delay,
        )

    @property
    def base_url(self) -> str:
        return self._sync.base_url

    def clear_cache(self) -> None:
        """清空结果缓存。"""
        self._sync.clear_cache()

    # ------------------------------------------------------------------ #
    # 底层
    # ------------------------------------------------------------------ #

    async def call(
        self, entry: str, body: Any | None = None, *, params: list[Any] | None = None
    ) -> F10Response:
        return await asyncio.to_thread(self._sync.call, entry, body, params=params)

    async def params(self, entry: str, *params: Any) -> F10Response:
        return await asyncio.to_thread(self._sync.params, entry, *params)

    # ------------------------------------------------------------------ #
    # 高层方法
    # ------------------------------------------------------------------ #

    async def stock_info(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.stock_info, code)

    async def business_periods(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.business_periods, code)

    async def topic_ids(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.topic_ids, code)

    async def company_profile(self, code: str, section: str = "8") -> F10Response:
        return await asyncio.to_thread(self._sync.company_profile, code, section)

    async def finance_report(self, code: str, report_type: str = "zcfzb") -> F10Response:
        return await asyncio.to_thread(self._sync.finance_report, code, report_type)

    async def finance_diagnosis(
        self, code: str, section: str = "yynl", scope: str = ""
    ) -> F10Response:
        return await asyncio.to_thread(self._sync.finance_diagnosis, code, section, scope)

    async def business_composition(self, code: str, report_date: str | None = None) -> F10Response:
        return await asyncio.to_thread(self._sync.business_composition, code, report_date)

    async def dividend_financing(self, code: str, section: str = "fh") -> F10Response:
        return await asyncio.to_thread(self._sync.dividend_financing, code, section)

    async def stock_score(self, code: str, section: str = "pf", arg: str = "") -> F10Response:
        return await asyncio.to_thread(self._sync.stock_score, code, section, arg)

    async def profit_forecast(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.profit_forecast, code)

    async def valuation(
        self, code: str, req_id: str | int = "200191", *, page: int = 0, page_size: int = 20
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.valuation, code, req_id, page=page, page_size=page_size
        )

    async def hot_topics(self, code: str, section: str = "zttzbkz") -> F10Response:
        return await asyncio.to_thread(self._sync.hot_topics, code, section)

    async def theme_market(
        self, code: str, req_id: str | int = "200743", *, page: int = -1, page_size: int = 10
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.theme_market, code, req_id, page=page, page_size=page_size
        )

    async def company_news(
        self, code: str, section: str = "gsyj", *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.company_news, code, section, page=page, page_size=page_size
        )

    async def company_news_all(
        self, code: str, section: str = "gsyj", *, page_size: int = 20, max_pages: int = 50
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._sync.company_news_all, code, section, page_size=page_size, max_pages=max_pages
        )

    async def northbound_holding(
        self, code: str, section: str = "bszj", *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.northbound_holding, code, section, page=page, page_size=page_size
        )

    async def ranking_detail(self, code: str, section: str = "scpmdela") -> F10Response:
        return await asyncio.to_thread(self._sync.ranking_detail, code, section)

    async def governance(self, code: str, section: str = "wgcl", arg: str = "") -> F10Response:
        return await asyncio.to_thread(self._sync.governance, code, section, arg)

    async def shareholder_change_plans(
        self, code: str, *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.shareholder_change_plans, code, page=page, page_size=page_size
        )

    async def shareholder_report_dates(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.shareholder_report_dates, code)

    async def top_shareholders(self, code: str, report_date: str = "") -> F10Response:
        return await asyncio.to_thread(self._sync.top_shareholders, code, report_date)

    async def institutional_holding(self, code: str, report_date: str = "") -> F10Response:
        return await asyncio.to_thread(self._sync.institutional_holding, code, report_date)

    async def shareholder_trend(self, code: str, page_size: int = 80) -> F10Response:
        return await asyncio.to_thread(self._sync.shareholder_trend, code, page_size)

    async def detail(self, detail_type: str, record_id: str | int) -> F10Response:
        return await asyncio.to_thread(self._sync.detail, detail_type, record_id)

    async def cache_list(self, code: str, kind: str = "gg") -> F10Response:
        return await asyncio.to_thread(self._sync.cache_list, code, kind)

    async def announcements(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.announcements, code)

    async def news(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.news, code)

    async def roadshows(self, code: str) -> F10Response:
        return await asyncio.to_thread(self._sync.roadshows, code)

    async def limit_up_down_list(
        self,
        start_date: str | int | None = None,
        end_date: str | int | None = None,
        *,
        include_summary: bool = False,
    ) -> F10Response:
        return await asyncio.to_thread(
            self._sync.limit_up_down_list, start_date, end_date, include_summary=include_summary
        )
