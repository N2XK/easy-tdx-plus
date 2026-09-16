"""tdxhub 网关的 F10 客户端（额外 F10 入口）。

`http://tdxhub.icfqs.com:7615/TQLEX` 与主网关同为 TQLEX 协议，额外提供
``TdxSharePCCW`` / ``TdxShareCW`` 命名空间的入口（股本结构、估值历史、题材概览等）。
参数形态与主网关略有差异，均已按实测确定。

用法::

    from easy_tdx.f10 import AltF10Client
    c = AltF10Client()
    df = c.share_capital_structure("600519")
"""

from __future__ import annotations

from .client import F10Client, _code6
from .entries import (
    ALT_TQLEX_BASE_URL,
    ENTRY_ALT_BALANCE_SHEET,
    ENTRY_ALT_BUSINESS_COMPOSITION,
    ENTRY_ALT_CASHFLOW_STATEMENT,
    ENTRY_ALT_HOT_TOPIC_OVERVIEW,
    ENTRY_ALT_INCOME_STATEMENT,
    ENTRY_ALT_INDUSTRY_RANK,
    ENTRY_ALT_INSTITUTIONAL_DETAIL,
    ENTRY_ALT_INSTITUTIONAL_PRICE,
    ENTRY_ALT_SHARE_CAPITAL,
    ENTRY_ALT_VALUATION_HISTORY,
)
from .models import F10Response
from .transport import TqlexTransport

__all__ = ["AltF10Client"]


class AltF10Client(F10Client):
    """指向 tdxhub 网关的 F10 客户端。"""

    def __init__(
        self,
        base_url: str = ALT_TQLEX_BASE_URL,
        timeout: float = 8.0,
        retries: int = 2,
        transport: TqlexTransport | None = None,
        cache: bool = False,
        cache_ttl: float = 60.0,
        empty_retries: int = 2,
        empty_retry_delay: float = 0.5,
    ) -> None:
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            retries=retries,
            transport=transport,
            cache=cache,
            cache_ttl=cache_ttl,
            empty_retries=empty_retries,
            empty_retry_delay=empty_retry_delay,
        )

    def share_capital_structure(self, code: str) -> F10Response:
        """股本结构变动历史（``gbjg``）。"""
        return self.params(ENTRY_ALT_SHARE_CAPITAL, _code6(code), "gbjg")

    def valuation_history(
        self, code: str, period: str = "1Y", indicator: str = "PE"
    ) -> F10Response:
        """估值历史序列（``ph_agf10_gzfx``）。

        Args:
            period: 区间，如 ``1Y`` / ``3Y`` / ``5Y``。
            indicator: 指标，如 ``PE`` / ``PB`` / ``PS``。
        """
        return self.params(ENTRY_ALT_VALUATION_HISTORY, _code6(code), period, indicator)

    def hot_topic_overview(self, code: str) -> F10Response:
        """热点题材信息面概览（``rdtc`` / ``xxmmg``）。"""
        return self.params(ENTRY_ALT_HOT_TOPIC_OVERVIEW, _code6(code), "xxmmg")

    def balance_sheet(self, code: str) -> F10Response:
        """资产负债表（``ph_agf10_cw_zcfzb``）；数据在 ``tables[1]``。"""
        return self.params(ENTRY_ALT_BALANCE_SHEET, _code6(code))

    def income_statement(self, code: str, *, single_quarter: bool = False) -> F10Response:
        """利润表（``ph_agf10_cw_lyb``）；数据在 ``tables[1]``。

        Args:
            single_quarter: True 为单季度，False 为报告期累计。
        """
        tag = "00102" if single_quarter else "00101"
        return self.params(ENTRY_ALT_INCOME_STATEMENT, tag, _code6(code))

    def cashflow_statement(self, code: str, *, single_quarter: bool = False) -> F10Response:
        """现金流量表（``ph_agf10_cw_xjllb``）；数据在 ``tables[1]``。"""
        tag = "00102" if single_quarter else "00101"
        return self.params(ENTRY_ALT_CASHFLOW_STATEMENT, tag, _code6(code))

    def business_composition(self, code: str, report_date: str | None = None) -> F10Response:
        """主营构成（``ph_agf10_jyfx``）。"""
        return self.params(ENTRY_ALT_BUSINESS_COMPOSITION, "00202", _code6(code), report_date or "")

    def industry_rank(
        self, code: str, report_date: str = "", *, valuation: bool = False
    ) -> F10Response:
        """行业排名（``ph_agf10_hypm``）。

        Args:
            valuation: True 为行业估值排名（00105），False 为行业财务排名（00102）。
        """
        key = "00105" if valuation else "00102"
        return self.params(ENTRY_ALT_INDUSTRY_RANK, key, _code6(code), report_date)

    def institutional_holding_detail(
        self, code: str, report_date: str = "", *, type_value: str = "99", page_size: int = 20
    ) -> F10Response:
        """机构持股明细（``gdyj_jgcgmx``）。

        Params: ``[code, sortType, reportDate, typeValue, clickIndex, pageNo, pageSize]``。
        """
        return self.params(
            ENTRY_ALT_INSTITUTIONAL_DETAIL,
            _code6(code),
            "0",
            report_date,
            str(type_value),
            "1",
            "1",
            str(page_size),
        )

    def institutional_holding_price_compare(
        self, code: str, *, query_key: str = "00101"
    ) -> F10Response:
        """机构持仓与股价对比（``ph_agf10_gbgd_jgcc``）。"""
        return self.params(ENTRY_ALT_INSTITUTIONAL_PRICE, query_key, _code6(code), "0")
