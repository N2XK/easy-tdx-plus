"""ICFQS 7615 TQLEX 客户端（龙虎榜 / 游资 / 每日复盘 / 题材）。

ICFQS 与 F10 共用 7615 TQLEX HTTP 网关，只是 host 与 Entry 不同。
参考 bensema/gotdx（MIT）的接口事实，独立实现。
"""

from __future__ import annotations

from typing import Any

from .models import F10Response
from .parse import parse_tqlex_response
from .transport import TqlexTransport

DEFAULT_ICFQS_ADDRESS = "121.37.193.4:7615"
DEFAULT_ICFQS_HOT_ADDRESS = "hot.icfqs.com:7615"

ENTRY_LHB = "CWServ.cfg_fx_yzlhb"
ENTRY_MRFP = "CWServ.cfg_tk_mrfp"
ENTRY_TOPIC = "CWServ.ph_tdxdatacenter_zttz_zy"
ENTRY_TOPIC_DETAIL = "CWServ.ph_tdxdatacenter_zttz_xqy"
ENTRY_TOPIC_KLINE = "CWServ.ph_tdxdatacenter_zttz_xqy_v2_qsid"
ENTRY_TOPIC_STOCKS = "CWServ.ph_tdxdatacenter_zttz_xggp"
ENTRY_TOPIC_NEW = "DataAggregation.zttz_xzgn2"
ENTRY_TOPIC_EVENTS = "DataAggregation.zttz_jhqz"
ENTRY_TOPIC_QUOTES = "HQServ.hq_nlp"
ENTRY_TOPIC_ROTATION = "HQServ.hq_nlp_copilot"
ENTRY_QUOTES_BATCH = "HQServ.PBCombHQ"

_HEADERS = {"Content-Type": "text/plain;charset=UTF-8"}


def _to_tqlex_base(address: str) -> str:
    base = address if "://" in address else f"http://{address}"
    return base.rstrip("/") + "/TQLEX"


# 需走 hot 网关的入口（龙虎榜 / 每日复盘）；题材等走默认网关。
_HOT_ENTRIES = frozenset({ENTRY_LHB, ENTRY_MRFP})


class IcfqsClient:
    """ICFQS TQLEX 客户端。

    部分入口部署在 ``hot.icfqs.com``（龙虎榜/复盘），其余在默认网关；本客户端按入口
    自动选网关，无需手动切换。

    Args:
        address: ``host:port`` 或完整 base URL（默认网关）。
        hot_address: 龙虎榜/复盘专用网关地址。
        timeout: 单次请求超时秒数。
        retries: 网络错误重试次数。
        transport: 自定义传输层（测试注入；注入时对全部入口生效）。
    """

    def __init__(
        self,
        address: str = DEFAULT_ICFQS_ADDRESS,
        timeout: float = 8.0,
        retries: int = 2,
        transport: TqlexTransport | None = None,
        hot_address: str = DEFAULT_ICFQS_HOT_ADDRESS,
    ) -> None:
        self.base_url = _to_tqlex_base(address)
        self.hot_base_url = _to_tqlex_base(hot_address)
        self._injected = transport is not None
        self._transport = transport or TqlexTransport(
            self.base_url,
            timeout=timeout,
            retries=retries,
            headers=_HEADERS,
            lenient_json=True,
        )
        self._hot_transport = transport or TqlexTransport(
            self.hot_base_url,
            timeout=timeout,
            retries=retries,
            headers=_HEADERS,
            lenient_json=True,
        )

    def _transport_for(self, entry: str) -> TqlexTransport:
        if not self._injected and entry in _HOT_ENTRIES:
            return self._hot_transport
        return self._transport

    # ------------------------------------------------------------------ #
    # 底层
    # ------------------------------------------------------------------ #

    def tql(self, entry: str, *params: Any) -> F10Response:
        """以 ``{"Params":[...], "oauth_zzfw":"1"}`` 形式调用。"""
        body = {"Params": list(params), "oauth_zzfw": "1"}
        return parse_tqlex_response(entry, body, self._transport_for(entry).post(entry, body))

    def post_json(self, entry: str, body: Any) -> F10Response:
        """以自定义 JSON body 调用。"""
        return parse_tqlex_response(entry, body, self._transport_for(entry).post(entry, body))

    # ------------------------------------------------------------------ #
    # 龙虎榜 / 游资
    # ------------------------------------------------------------------ #

    def lhb_detail(self, symbol: str, start_date: str, end_date: str) -> F10Response:
        """个股龙虎榜明细（symbol 为 6 位代码）。"""
        return self.tql(ENTRY_LHB, "yybxq", start_date, end_date, symbol, "", 0, 2000)

    def lhb_yyb_detail(self, yyb_name: str, start_date: str, end_date: str) -> F10Response:
        """营业部龙虎榜明细。"""
        return self.tql(ENTRY_LHB, "tjyyb", start_date, end_date, "", yyb_name, 0, 2000)

    def lhb_yz_detail(self, code: str, start_date: str, end_date: str) -> F10Response:
        """游资明细。"""
        return self.tql(ENTRY_LHB, "yzxq", start_date, end_date, code, "", 0, 2000)

    # ------------------------------------------------------------------ #
    # 每日复盘
    # ------------------------------------------------------------------ #

    def daily_review(self, review_type: str, date: str = "0", limit: int = 30) -> F10Response:
        """每日复盘（review_type 如 ``rq`` 等，date='0' 表示最新）。"""
        return self.tql(ENTRY_MRFP, date, review_type, "", 0, limit)

    def daily_review_latest_date(self) -> F10Response:
        """最新可用的每日复盘日期。"""
        return self.tql(ENTRY_MRFP, "0", "rq", "", 0, 30)

    # ------------------------------------------------------------------ #
    # 题材 / 主题
    # ------------------------------------------------------------------ #

    def topic_list(self, category: str, setcode: str, page: int = 1) -> F10Response:
        """题材列表（分页）。"""
        return self.tql(ENTRY_TOPIC, "00601", f"{category}|{setcode}", max(1, page))

    def topic_search(self, keyword: str) -> F10Response:
        """题材搜索。"""
        return self.tql(ENTRY_TOPIC, "00102", keyword, "0")

    def topics_new(self) -> F10Response:
        """新题材。"""
        return self.tql(ENTRY_TOPIC_NEW, "01001", "", 1)

    def topics_hot(self) -> F10Response:
        """热点题材。"""
        return self.tql(ENTRY_TOPIC, "00302", "", 1)

    def topics_events(self) -> F10Response:
        """题材事件。"""
        return self.tql(ENTRY_TOPIC_EVENTS, "00401", "", 10)

    def topics_top(self, top_n: int = 10) -> F10Response:
        """龙头题材。"""
        return self.tql(ENTRY_TOPIC, "00101", "", top_n or 10)

    def topic_detail(self, code: str, setcode: str) -> F10Response:
        """题材详情。"""
        return self.tql(ENTRY_TOPIC_DETAIL, "00301", code, setcode)

    def topic_kline(self, code: str, setcode: str) -> F10Response:
        """题材走势。"""
        return self.tql(ENTRY_TOPIC_KLINE, "00501", code, 3, "", setcode)

    def topic_stocks(self, code: str, setcode: str, page: int = 1, size: int = 20) -> F10Response:
        """题材成分股。"""
        return self.tql(ENTRY_TOPIC_STOCKS, "00901", code, setcode, 1, size or 20, 0, max(1, page))

    def topic_quotes(self, codes: list[tuple[str, str]]) -> F10Response:
        """题材/批量行情快照（codes 为 (setcode, code) 列表）。"""
        setcodes = [c[0] for c in codes]
        values = [c[1] for c in codes]
        body = [
            {
                "ReqId": "200800",
                "modname": "module_misc.dll",
                "Code": values,
                "PageSize": str(len(values)),
                "Page": "0",
                "Desc": "0",
                "Setcode": setcodes,
                "Sort": "0",
            }
        ]
        return self.post_json(ENTRY_TOPIC_QUOTES, body)

    def topic_rotation(
        self,
        data_num: int = 1,
        data_type: int = 1,
        data_date: int = 2,
        theme_type: str = "0",
    ) -> F10Response:
        """题材轮动。"""
        body = [
            {
                "ReqId": "200773",
                "modname": "mod_copilot.dll",
                "dataDate": str(data_date),
                "dataType": str(data_type),
                "dataNum": str(data_num),
                "themeType": theme_type,
            }
        ]
        return self.post_json(ENTRY_TOPIC_ROTATION, body)

    def quotes_batch(
        self, codes: list[tuple[str, str]], want_columns: list[str] | None = None
    ) -> F10Response:
        """批量行情快照（codes 为 (setcode, code) 列表）。"""
        body = {
            "Setcode": [c[0] for c in codes],
            "Head": {"Target": 0},
            "WantCol": want_columns or ["CLOSE", "NOW"],
            "Code": [c[1] for c in codes],
        }
        return self.post_json(ENTRY_QUOTES_BATCH, body)
