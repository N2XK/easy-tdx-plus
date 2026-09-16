"""TQLEX Entry 常量。"""

from __future__ import annotations

DEFAULT_TQLEX_BASE_URL = "http://static.tdx.com.cn:7615/TQLEX"
DEFAULT_LIMIT_BOARD_BASE_URL = "http://hot.icfqs.com:7615/TQLEX"
# tdxhub 网关：同 TQLEX 协议，额外提供 TdxSharePCCW / TdxShareCW 命名空间的 F10 入口
ALT_TQLEX_BASE_URL = "http://tdxhub.icfqs.com:7615/TQLEX"
DEFAULT_QSID = "tdx"

ENTRY_STOCK_INFO = "CWServ.tdxf10_gg_comreq"
ENTRY_COMPANY_PROFILE = "CWServ.tdxf10_gg_gsgk"
ENTRY_BUSINESS_COMPOSITION = "CWServ.tdxf10_gg_jyfx"
ENTRY_SHAREHOLDER_CHANGE = "CWServ.tdxf10_gg_gdyj"
ENTRY_DIVIDEND_FINANCING = "CWServ.tdxf10_gg_fhrz"
ENTRY_ALLOTMENT = "CWServ.tdxf10_gg_fhrz_zfhpmx"
ENTRY_FINANCE_REPORT = "CWServ.tdxf10_gg_cwfx"
ENTRY_FINANCE_DIAGNOSIS = "CWServ.tdxf10_gg_cwzd"
ENTRY_STOCK_SCORE = "CWServ.tdxf10_gg_ggzp"
ENTRY_PROFIT_FORECAST = "CWServ.tdxf10_gg_ybpj"
ENTRY_RANKING_DETAIL = "CWServ.tdxf10_gg_zxts_rqpm"
ENTRY_GOVERNANCE = "CWServ.tdxf10_gg_zbyz"
ENTRY_HOT_TOPICS = "CWServ.tdxf10_gg_rdtc"
ENTRY_TOPIC_COMPARE = "CWServ.tdxf10_gg_rdtc_gndb"
ENTRY_COMPANY_NEWS = "CWServ.tdxf10_gg_gszx"
ENTRY_NORTHBOUND = "CWServ.tdxf10_gg_zlcc"
ENTRY_DETAIL = "CWServ.tdxf10_gg_idreq"
ENTRY_CACHE = "CWSearch.tzx_rcache"
ENTRY_LIMIT_BOARD_LADDER = "CWServ.cfg_fx_lbtt"
ENTRY_THEME_MARKET = "HQServ.hq_nlp_tcihq"
ENTRY_VALUATION = "HQServ.hq_nlp_gpsj"

# tdxhub（ALT_TQLEX_BASE_URL）额外入口
ENTRY_ALT_SHARE_CAPITAL = "TdxSharePCCW.tdxf10_gg_gbjg"
ENTRY_ALT_VALUATION_HISTORY = "TdxShareCW.ph_agf10_gzfx"
ENTRY_ALT_HOT_TOPIC_OVERVIEW = "TdxSharePCCW.tdxf10_gg_rdtc"
ENTRY_ALT_BALANCE_SHEET = "TdxShareCW.ph_agf10_cw_zcfzb"
ENTRY_ALT_INCOME_STATEMENT = "TdxShareCW.ph_agf10_cw_lyb"
ENTRY_ALT_CASHFLOW_STATEMENT = "TdxShareCW.ph_agf10_cw_xjllb"
ENTRY_ALT_BUSINESS_COMPOSITION = "TdxShareCW.ph_agf10_jyfx"
ENTRY_ALT_INDUSTRY_RANK = "TdxShareCW.ph_agf10_hypm"
ENTRY_ALT_INSTITUTIONAL_DETAIL = "TdxSharePCCW.tdxf10_gg_gdyj_jgcgmx"
ENTRY_ALT_INSTITUTIONAL_PRICE = "TdxShareCW.ph_agf10_gbgd_jgcc"

MARKET_TO_ID = {"sz": 0, "sh": 1, "bj": 2}
