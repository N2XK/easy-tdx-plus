"""F10 / TQLEX（7615）高层客户端。

独立实现（协议事实参考公开文档）：7615 是 HTTP 网关，
``POST <base>?Entry=<entry>``，body ``{"Params":[...]}`` 或自定义 JSON。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .entries import (
    DEFAULT_LIMIT_BOARD_BASE_URL,
    DEFAULT_QSID,
    DEFAULT_TQLEX_BASE_URL,
    ENTRY_ALLOTMENT,
    ENTRY_BUSINESS_COMPOSITION,
    ENTRY_CACHE,
    ENTRY_COMPANY_NEWS,
    ENTRY_COMPANY_PROFILE,
    ENTRY_DETAIL,
    ENTRY_DIVIDEND_FINANCING,
    ENTRY_FINANCE_DIAGNOSIS,
    ENTRY_FINANCE_REPORT,
    ENTRY_GOVERNANCE,
    ENTRY_HOT_TOPICS,
    ENTRY_LIMIT_BOARD_LADDER,
    ENTRY_NORTHBOUND,
    ENTRY_PROFIT_FORECAST,
    ENTRY_RANKING_DETAIL,
    ENTRY_SHAREHOLDER_CHANGE,
    ENTRY_STOCK_INFO,
    ENTRY_STOCK_SCORE,
    ENTRY_THEME_MARKET,
    ENTRY_TOPIC_COMPARE,
    ENTRY_VALUATION,
    MARKET_TO_ID,
)
from .models import F10Response
from .parse import parse_tqlex_response
from .transport import TqlexTransport

_SH_PREFIX = {"5", "6", "9"}
_BJ_PREFIX = {"4", "8"}


def _market_id(market: str) -> int:
    return MARKET_TO_ID[market]


def split_code(code: str) -> tuple[int, str, str]:
    """将代码规范化为 (market_id, market, code6)。

    支持 ``"600519"`` / ``"sh600519"`` / ``"SH.600519"`` 等形式。
    无前缀时按首位推断（6/5/9→沪，4/8→北，其余→深）。
    """
    text = code.strip().lower().replace(".", "")
    market = None
    for prefix in ("sh", "sz", "bj"):
        if text.startswith(prefix):
            market = prefix
            text = text[2:]
            break
    if market is None:
        head = text[:1]
        market = "sh" if head in _SH_PREFIX else ("bj" if head in _BJ_PREFIX else "sz")
    return _market_id(market), market, text


def _code6(code: str) -> str:
    return split_code(code)[2]


class F10Client:
    """7615 F10 / TQLEX 客户端。

    Args:
        base_url: TQLEX 网关基址。
        timeout: 单次请求超时秒数。
        retries: 网络错误重试次数。
        transport: 自定义传输层（用于测试注入）。
    """

    def __init__(
        self,
        base_url: str = DEFAULT_TQLEX_BASE_URL,
        timeout: float = 8.0,
        retries: int = 2,
        transport: TqlexTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self.limit_board_base_url = (
            DEFAULT_LIMIT_BOARD_BASE_URL if base_url == DEFAULT_TQLEX_BASE_URL else base_url
        )
        self._transport = transport or TqlexTransport(base_url, timeout=timeout, retries=retries)
        self._injected = transport is not None

    # ------------------------------------------------------------------ #
    # 底层调用
    # ------------------------------------------------------------------ #

    def call(
        self, entry: str, body: Any | None = None, *, params: list[Any] | None = None
    ) -> F10Response:
        """调用任意 TQLEX Entry。"""
        if body is not None and params is not None:
            raise ValueError("body 与 params 只能传一个")
        request_body = {"Params": list(params)} if params is not None else (body or {})
        base = self.limit_board_base_url if entry == ENTRY_LIMIT_BOARD_LADDER else self.base_url
        raw = self._transport_for(base).post(entry, request_body)
        return parse_tqlex_response(entry, request_body, raw)

    def _transport_for(self, base: str) -> TqlexTransport:
        if self._injected or base == self._transport.base_url:
            return self._transport
        return TqlexTransport(
            base, timeout=self._transport.timeout, retries=self._transport.retries
        )

    def params(self, entry: str, *params: Any) -> F10Response:
        """以 ``{"Params": [...]}`` 形式调用 Entry。"""
        return self.call(entry, params=list(params))

    # ------------------------------------------------------------------ #
    # 基础信息
    # ------------------------------------------------------------------ #

    def stock_info(self, code: str) -> F10Response:
        """股票基础信息（名称 / 代码 / 市场）。"""
        return self.params(ENTRY_STOCK_INFO, "gpquery", _code6(code))

    def business_periods(self, code: str) -> F10Response:
        """主营构成可选报告期。"""
        return self.params(ENTRY_STOCK_INFO, "zygcfx", _code6(code))

    def topic_ids(self, code: str) -> F10Response:
        """股票关联题材 ID 列表。"""
        return self.params(ENTRY_STOCK_INFO, "rdtcgn", _code6(code))

    def company_profile(self, code: str, section: str = "8") -> F10Response:
        """公司概况（发行上市信息）。"""
        return self.params(ENTRY_COMPANY_PROFILE, section, _code6(code), "")

    # ------------------------------------------------------------------ #
    # 财务
    # ------------------------------------------------------------------ #

    def finance_report(self, code: str, report_type: str = "zcfzb") -> F10Response:
        """财务报表（默认资产负债表 zcfzb）。"""
        return self.params(ENTRY_FINANCE_REPORT, _code6(code), report_type, "")

    def finance_diagnosis(self, code: str, section: str = "yynl", scope: str = "") -> F10Response:
        """财务诊断（yynl/ylnl/cznl/xjll/zczl 等）。"""
        return self.params(ENTRY_FINANCE_DIAGNOSIS, section, _code6(code), scope)

    def business_composition(self, code: str, report_date: str | None = None) -> F10Response:
        """主营构成。不传报告期时自动取服务端最新期。"""
        code6 = _code6(code)
        selected = report_date or self._first_value(self.business_periods(code6), "T002")
        if selected is None:
            selected = ""
        return self.params(ENTRY_BUSINESS_COMPOSITION, code6, "zygc", str(selected))

    def dividend_financing(self, code: str, section: str = "fh") -> F10Response:
        """分红融资（默认分红方案历史）。"""
        return self.params(ENTRY_DIVIDEND_FINANCING, _code6(code), section)

    def allotment_dates(self, code: str) -> F10Response:
        """增发获配可选日期。"""
        return self.params(ENTRY_ALLOTMENT, "zfpg_bgq", _code6(code), "")

    def allotment_details(self, code: str, allotment_date: str) -> F10Response:
        """指定增发日期的获配机构明细。"""
        return self.params(ENTRY_ALLOTMENT, "zfpg", _code6(code), allotment_date)

    def topic_compare(
        self, code: str, topic_id: str | int, section: str = "gndbzfsj", sort_by: str = "zdf"
    ) -> F10Response:
        """题材内对比排名。"""
        return self.params(ENTRY_TOPIC_COMPARE, section, _code6(code), str(topic_id), sort_by)

    def stock_score(self, code: str, section: str = "pf", arg: str = "") -> F10Response:
        """个股总评（默认综合评分）。"""
        return self.params(ENTRY_STOCK_SCORE, section, _code6(code), arg, "")

    def profit_forecast(self, code: str) -> F10Response:
        """盈利预测评级统计。"""
        return self.params(ENTRY_PROFIT_FORECAST, _code6(code), "ylyctj")

    # ------------------------------------------------------------------ #
    # 估值 / 题材 / 资讯
    # ------------------------------------------------------------------ #

    def valuation(
        self, code: str, req_id: str | int = "200191", *, page: int = 0, page_size: int = 20
    ) -> F10Response:
        """估值市场数据（PE/PB/市销率/百分位/市值等）。"""
        market_id, _, code6 = split_code(code)
        payload = {
            "ReqId": str(req_id),
            "Code": f"{code6}|{market_id}",
            "BeginDate": "0",
            "EndDate": "0",
            "Page": str(page),
            "PageSize": str(page_size),
            "modname": "mod_gpsj.dll",
        }
        return self.call(ENTRY_VALUATION, [payload])

    def hot_topics(self, code: str, section: str = "zttzbkz") -> F10Response:
        """热点题材（关联题材 / 入选原因）。"""
        return self.params(ENTRY_HOT_TOPICS, _code6(code), section)

    def theme_market(
        self, code: str, req_id: str | int = "200743", *, page: int = -1, page_size: int = 10
    ) -> F10Response:
        """题材概念行情（相关板块 / 主力资金等）。"""
        market_id, _, code6 = split_code(code)
        payload = {
            "ReqId": str(req_id),
            "setcode": market_id,
            "code": code6,
            "Page": page,
            "PageSize": str(page_size),
            "modname": "mod_tcihq.dll",
        }
        return self.call(ENTRY_THEME_MARKET, [payload])

    def company_news(
        self,
        code: str,
        section: str = "gsyj",
        *,
        keyword: str = "",
        rating: str | int = "0",
        page: int = 1,
        page_size: int = 20,
    ) -> F10Response:
        """公司资讯（gsyj 研报 / jgcs 监管措施）。"""
        return self.params(
            ENTRY_COMPANY_NEWS,
            _code6(code),
            section,
            keyword,
            str(rating),
            str(page),
            str(page_size),
        )

    def northbound_holding(
        self,
        code: str,
        section: str = "bszj",
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> F10Response:
        """沪深股通持股变化。"""
        return self.params(
            ENTRY_NORTHBOUND, _code6(code), section, "", str(page), str(page), str(page_size)
        )

    def shareholder_change_plans(
        self, code: str, *, page: int = 1, page_size: int = 20
    ) -> F10Response:
        """股东增减持计划。"""
        return self.params(
            ENTRY_SHAREHOLDER_CHANGE,
            _code6(code),
            "gdzjcjh",
            "",
            "",
            str(page),
            str(page),
            str(page_size),
        )

    def ranking_detail(self, code: str, section: str = "scpmdela") -> F10Response:
        """市场 / 行业排名明细。"""
        return self.params(ENTRY_RANKING_DETAIL, _code6(code), section)

    def governance(self, code: str, section: str = "wgcl", arg: str = "") -> F10Response:
        """资本运作治理（wgcl 违规处理 / dbmx 担保明细）。"""
        return self.params(ENTRY_GOVERNANCE, section, _code6(code), arg)

    def detail(self, detail_type: str, record_id: str | int) -> F10Response:
        """按记录 ID 查询详情正文。"""
        return self.params(ENTRY_DETAIL, detail_type, str(record_id))

    # ------------------------------------------------------------------ #
    # 公告 / 新闻 / 路演
    # ------------------------------------------------------------------ #

    def cache_list(self, code: str, kind: str = "gg") -> F10Response:
        """新闻/公告/路演缓存列表（kind: gg/xw/ly）。"""
        if kind not in {"gg", "xw", "ly"}:
            raise ValueError("kind 必须是 gg / xw / ly 之一")
        market_id, _, code6 = split_code(code)
        body = {
            "action": "get",
            "key": f"{kind}:{market_id}_{code6}",
            "bin": "1",
            "qsid": DEFAULT_QSID,
        }
        return self.call(ENTRY_CACHE, body)

    def announcements(self, code: str) -> F10Response:
        """公告列表。"""
        return self.cache_list(code, "gg")

    def news(self, code: str) -> F10Response:
        """新闻列表。"""
        return self.cache_list(code, "xw")

    def roadshows(self, code: str) -> F10Response:
        """路演列表。"""
        return self.cache_list(code, "ly")

    # ------------------------------------------------------------------ #
    # 涨跌停榜
    # ------------------------------------------------------------------ #

    def limit_up_down_list(
        self,
        start_date: str | int | None = None,
        end_date: str | int | None = None,
        *,
        include_summary: bool = False,
    ) -> F10Response:
        """逐股涨停/炸板/跌停列表；``include_summary`` 时附带市场概况。

        返回首张表为明细；``include_summary`` 时概况在第二张表。
        """
        start, end = self._normalize_dates(start_date, end_date)
        detail = self.params(ENTRY_LIMIT_BOARD_LADDER, "1", start, end)
        if not include_summary:
            return detail
        summary = self.params(ENTRY_LIMIT_BOARD_LADDER, "2", start, end)
        return F10Response(
            entry=detail.entry,
            request_body=detail.request_body,
            error_code=detail.error_code,
            result_sets=detail.result_sets + summary.result_sets,
            raw=detail.raw,
        )

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    @staticmethod
    def _first_value(response: F10Response, field_name: str) -> Any | None:
        for row in response.rows:
            if field_name in row:
                return row[field_name]
        return None

    @staticmethod
    def _normalize_dates(
        start_date: str | int | date | None, end_date: str | int | date | None
    ) -> tuple[str, str]:
        start = _date_text(start_date)
        end = _date_text(end_date)
        if start is None and end is None:
            today = date.today().strftime("%Y%m%d")
            return today, today
        if start is None:
            start = end
        if end is None:
            end = start
        assert start is not None and end is not None
        if start > end:
            raise ValueError("start_date 不能晚于 end_date")
        return start, end


def _date_text(value: str | int | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).replace("-", "")
