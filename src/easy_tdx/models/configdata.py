"""配置类加工数据模型（来自 zhb.zip / tdxhy.cfg）。

字段语义参考 injoyai/tdx（MIT）；未官方文档化的字段保留在 ``_fields`` 中，
不做强制命名，供使用者自行取用。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TdxStat:
    """个股综合统计指标（来自 tdxstat.cfg，35 字段）。"""

    market: int  # 市场 0=深 1=沪 2=京
    code: str
    date: str  # YYYYMMDD
    pe_ttm: float  # 市盈率(TTM)
    trend_days: int  # 连涨连跌天数（正涨负跌）
    change_pct: float  # 涨跌幅 %
    pe_static: float  # 静态市盈率
    div_yield: float  # 股息率 %
    chg_5: float  # 5 日涨跌幅 %
    chg_10: float  # 10 日涨跌幅 %
    chg_20: float  # 20 日涨跌幅 %
    chg_60: float  # 60 日涨跌幅 %
    chg_ytd: float  # 年初至今涨跌幅 %
    _fields: list[str] = field(default_factory=list, repr=False)


@dataclass
class TdxStat2:
    """个股资金流向 + 板块归属（来自 tdxstat2.cfg，21 字段）。"""

    market: int
    code: str
    date: str
    block_index: str  # 板块指数代码(id)，可能为空
    amount: float  # 今日成交额（万元）
    amount_prev: float  # 昨日成交额（万元）
    ipo_price: float  # IPO 发行价（元）
    high_52w: float  # 52 周最高价（元）
    low_52w: float  # 52 周最低价（元）
    _fields: list[str] = field(default_factory=list, repr=False)


@dataclass
class TdxXgsg:
    """新股申购信息（来自 xgsg.cfg，18 字段）。"""

    market: int
    code: str  # 申购代码
    date: str  # 申购日期 YYYYMMDD
    issue_price: float  # 发行价
    name: str
    _fields: list[str] = field(default_factory=list, repr=False)


@dataclass
class SpBlock:
    """专业板块及其成分（来自 spblock.dat）。"""

    name: str
    codes: list[str]  # 7 字符 "市场+代码"，如 "0000011"（市场0=深/1=沪/2=北）
    index: str = ""  # 板块指数代码(id)，经 tdxzs/tdxbk 关联后回填


@dataclass
class TdxZs:
    """板块指数配置（来自 tdxzs.cfg）。"""

    name: str
    code: str  # 板块指数代码，如 880xxx / 881xxx
    type: int = 0
    sub_type: int = 0
    ref: str = ""


@dataclass
class TdxBk:
    """板块简称 ↔ 全称（来自 tdxbk.cfg）。"""

    short: str
    full: str


@dataclass
class TdxHy:
    """行业归属（来自 tdxhy.cfg）。"""

    market: int
    code: str
    tdx_hy: str  # 通达信新行业代码（T 前缀）
    sw_hy: str  # 申万行业代码（X 前缀）


@dataclass
class TdxAhRate:
    """A/H 股对照（来自 tdxahrate.cfg）。"""

    name: str
    a_code: str  # A 股代码，如 002594
    h_code: str  # H 股代码，如 01211
    flag: int = 0


@dataclass
class TdxAdr:
    """境外上市对照（来自 tdxadr.cfg）：港股/中概 ↔ ADR 代码。"""

    name: str
    code: str  # 港股/中概代码
    adr: str  # ADR 交易代码，如 BABA
    flag: int = 0


@dataclass
class TdxChain:
    """产业链板块（来自 tdxchain.cfg）。"""

    code: str  # 板块指数代码，如 880506
    cyl_code: str  # 产业链代码，如 CYL00210
    name: str


@dataclass
class NamedBlock:
    """具名板块成分（来自 jjblock.dat / mgblock.dat / hkblock.dat / csiblock.dat）。

    文件以 ``#板块名`` 分行，随后每行一个成分（``市场,代码`` 或纯代码）。
    """

    name: str
    codes: list[str]
