"""7615 F10 / TQLEX 异步客户端。

默认复用同步 :class:`F10Client`（在线程池中执行 HTTP）；传入
``native_http=True`` 时，底层请求使用原生 asyncio HTTP 传输，同时复用同步
客户端的参数构造和解析逻辑。
"""

from __future__ import annotations

import asyncio
from typing import Any, TypeVar, cast

from .client import F10Client
from .entries import DEFAULT_TQLEX_BASE_URL
from .models import F10Response
from .transport import AsyncTqlexTransport, TqlexTransport

_R = TypeVar("_R")


class _CapturedRequest(Exception):
    def __init__(self, entry: str, body: Any) -> None:
        super().__init__(entry)
        self.entry = entry
        self.body = body


class _CaptureTransport(TqlexTransport):
    """让同步 F10 高层方法只构造请求，不执行网络 IO。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.timeout = 0.0
        self.retries = 0

    def post(self, entry: str, body: Any) -> dict[str, Any]:
        raise _CapturedRequest(entry, body)


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
        native_http: bool = False,
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
        self._async_transport = (
            AsyncTqlexTransport(base_url, timeout=timeout, retries=retries) if native_http else None
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
        if self._async_transport is not None:
            if body is not None and params is not None:
                raise ValueError("body 与 params 只能传一个")
            request_body = {"Params": list(params)} if params is not None else (body or {})
            raw = await self._async_transport.post(entry, request_body)
            from .parse import parse_tqlex_response

            return parse_tqlex_response(entry, request_body, raw)
        return await asyncio.to_thread(self._sync.call, entry, body, params=params)

    async def params(self, entry: str, *params: Any) -> F10Response:
        return await self.call(entry, params=list(params))

    async def aclose(self) -> None:
        """关闭原生异步 HTTP 传输；线程包装模式无需显式关闭。"""
        if self._async_transport is not None:
            await self._async_transport.aclose()

    async def _invoke(self, method: str, *args: Any, **kwargs: Any) -> _R:
        """执行一个高层方法；native_http 模式只在线程中构造请求。"""
        if self._async_transport is None:
            return cast(_R, await asyncio.to_thread(getattr(self._sync, method), *args, **kwargs))
        capture = F10Client(self.base_url, transport=_CaptureTransport(self.base_url))
        try:
            getattr(capture, method)(*args, **kwargs)
        except _CapturedRequest as request:
            raw = await self._async_transport.post(request.entry, request.body)
            from .parse import parse_tqlex_response

            return cast(_R, parse_tqlex_response(request.entry, request.body, raw))
        raise RuntimeError(f"native F10 method {method} did not issue a request")

    # ------------------------------------------------------------------ #
    # 高层方法
    # ------------------------------------------------------------------ #

    async def stock_info(self, code: str) -> F10Response:
        return await self._invoke("stock_info", code)

    async def business_periods(self, code: str) -> F10Response:
        return await self._invoke("business_periods", code)

    async def topic_ids(self, code: str) -> F10Response:
        return await self._invoke("topic_ids", code)

    async def company_profile(self, code: str, section: str = "8") -> F10Response:
        return await self._invoke("company_profile", code, section)

    async def finance_report(self, code: str, report_type: str = "zcfzb") -> F10Response:
        return await self._invoke("finance_report", code, report_type)

    async def finance_diagnosis(
        self, code: str, section: str = "yynl", scope: str = ""
    ) -> F10Response:
        return await self._invoke("finance_diagnosis", code, section, scope)

    async def business_composition(self, code: str, report_date: str | None = None) -> F10Response:
        if self._async_transport is not None and report_date is None:
            # 需要先查询最新报告期，保留同步组合逻辑。
            return await asyncio.to_thread(self._sync.business_composition, code, report_date)
        return await self._invoke("business_composition", code, report_date)

    async def dividend_financing(self, code: str, section: str = "fh") -> F10Response:
        return await self._invoke("dividend_financing", code, section)

    async def allotment_dates(self, code: str) -> F10Response:
        return await self._invoke("allotment_dates", code)

    async def allotment_details(self, code: str, allotment_date: str) -> F10Response:
        return await self._invoke("allotment_details", code, allotment_date)

    async def topic_compare(
        self, code: str, topic_id: str | int, section: str = "gndbzfsj", sort_by: str = "zdf"
    ) -> F10Response:
        return await self._invoke("topic_compare", code, topic_id, section=section, sort_by=sort_by)

    async def stock_score(self, code: str, section: str = "pf", arg: str = "") -> F10Response:
        return await self._invoke("stock_score", code, section, arg)

    async def profit_forecast(self, code: str) -> F10Response:
        return await self._invoke("profit_forecast", code)

    async def valuation(
        self, code: str, req_id: str | int = "200191", *, page: int = 0, page_size: int = 20
    ) -> F10Response:
        return await self._invoke("valuation", code, req_id, page=page, page_size=page_size)

    async def hot_topics(self, code: str, section: str = "zttzbkz") -> F10Response:
        return await self._invoke("hot_topics", code, section)

    async def theme_market(
        self, code: str, req_id: str | int = "200743", *, page: int = -1, page_size: int = 10
    ) -> F10Response:
        return await self._invoke("theme_market", code, req_id, page=page, page_size=page_size)

    async def company_news(
        self,
        code: str,
        section: str = "gsyj",
        *,
        keyword: str = "",
        rating: str | int = "0",
        page: int = 1,
        page_size: int = 20,
    ) -> F10Response:
        return await self._invoke(
            "company_news",
            code,
            section,
            keyword=keyword,
            rating=rating,
            page=page,
            page_size=page_size,
        )

    async def company_news_all(
        self,
        code: str,
        section: str = "gsyj",
        *,
        keyword: str = "",
        rating: str | int = "0",
        page_size: int = 20,
        max_pages: int = 50,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._sync.company_news_all,
            code,
            section,
            keyword=keyword,
            rating=rating,
            page_size=page_size,
            max_pages=max_pages,
        )

    async def northbound_holding(
        self, code: str, section: str = "bszj", *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        return await self._invoke(
            "northbound_holding", code, section, page=page, page_size=page_size
        )

    async def ranking_detail(self, code: str, section: str = "scpmdela") -> F10Response:
        return await self._invoke("ranking_detail", code, section)

    async def governance(self, code: str, section: str = "wgcl", arg: str = "") -> F10Response:
        return await self._invoke("governance", code, section, arg)

    async def shareholder_change_plans(
        self, code: str, *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        return await self._invoke("shareholder_change_plans", code, page=page, page_size=page_size)

    async def shareholder_report_dates(self, code: str) -> F10Response:
        return await self._invoke("shareholder_report_dates", code)

    async def top_shareholders(self, code: str, report_date: str = "") -> F10Response:
        return await self._invoke("top_shareholders", code, report_date)

    async def institutional_holding(self, code: str, report_date: str = "") -> F10Response:
        return await self._invoke("institutional_holding", code, report_date)

    async def shareholder_trend(self, code: str, page_size: int = 80) -> F10Response:
        return await self._invoke("shareholder_trend", code, page_size)

    async def shareholder_count(
        self, code: str, report_date: str = "", page_size: int = 50
    ) -> F10Response:
        return await self._invoke("shareholder_count", code, report_date, page_size)

    async def shareholder_count_rank(self, code: str, report_date: str = "") -> F10Response:
        return await self._invoke("shareholder_count_rank", code, report_date)

    async def detail(self, detail_type: str, record_id: str | int) -> F10Response:
        return await self._invoke("detail", detail_type, record_id)

    async def cache_list(self, code: str, kind: str = "gg") -> F10Response:
        return await self._invoke("cache_list", code, kind)

    async def announcements(self, code: str) -> F10Response:
        return await self._invoke("announcements", code)

    async def news(self, code: str) -> F10Response:
        return await self._invoke("news", code)

    async def roadshows(self, code: str) -> F10Response:
        return await self._invoke("roadshows", code)

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
