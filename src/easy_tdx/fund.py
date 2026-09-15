"""基金（ETF/LOF/REITs/分级/债券基金）辅助。

标准协议不区分品种，这里按代码前缀分类，并复用行情/K 线接口。
"""

from __future__ import annotations

from .models.enums import Market

__all__ = ["classify_fund", "is_fund", "FUND_TYPES"]

# 类型 → 代码前缀
FUND_TYPES: dict[str, tuple[str, ...]] = {
    "etf": (
        "510",
        "511",
        "512",
        "513",
        "515",
        "516",
        "518",
        "560",
        "561",
        "562",
        "563",
        "588",
        "159",
    ),
    "lof": (
        "501",
        "502",
        "160",
        "161",
        "162",
        "163",
        "164",
        "165",
        "166",
        "167",
        "168",
        "169",
    ),
    "reits": ("508",),
    "bond_fund": ("511", "110", "113"),
    "otc": ("519",),
}


def classify_fund(code: str) -> str | None:
    """按代码前缀返回基金类型，非基金返回 ``None``。

    顺序：reits → etf → bond_fund → lof → otc。
    """
    text = code.strip().lower()
    for prefix in ("sh", "sz", "bj"):
        if text.startswith(prefix):
            text = text[2:]
            break
    text = text.split(".")[0]
    for kind in ("reits", "etf", "bond_fund", "lof", "otc"):
        if text.startswith(FUND_TYPES[kind]):
            return kind
    return None


def is_fund(code: str) -> bool:
    return classify_fund(code) is not None


def filter_fund_stocks(stocks: list[tuple[Market, str]]) -> list[tuple[Market, str]]:
    """过滤出基金代码。"""
    return [(m, c) for m, c in stocks if is_fund(c)]
