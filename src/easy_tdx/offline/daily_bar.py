"""日线 K 线数据读取（.day 文件）。"""

import struct
from pathlib import Path

import numpy as np
import pandas as pd

from ..exceptions import TdxFileNotFoundError
from ..models.bar import SecurityBar
from .paths import _market_to_exchange, resolve_vipdoc

# struct 格式：日期(YYYYMMDD) 开盘 最高 最低 收盘 成交额 成交量 保留
# 全部为小端序，32 字节/条
_DAILY_FMT = struct.Struct("<IIIIIfII")

# numpy 结构化 dtype（与 _DAILY_FMT 等价），用于整块向量化解析
_DAILY_DTYPE = np.dtype(
    [
        ("date", "<u4"),
        ("open", "<u4"),
        ("high", "<u4"),
        ("low", "<u4"),
        ("close", "<u4"),
        ("amount", "<f4"),
        ("vol", "<u4"),
        ("reserved", "<u4"),
    ]
)

# 证券类型 → (价格系数, 量系数)（与 mootdx/通达信本地口径一致）
_SECURITY_COEFFICIENTS: dict[str, tuple[float, float]] = {
    "SH_A_STOCK": (0.01, 0.01),
    "SH_B_STOCK": (0.001, 0.01),
    "SH_STAR_STOCK": (0.01, 0.01),
    "SH_INDEX": (0.01, 1.0),
    "SH_FUND": (0.001, 1.0),
    "SH_BOND": (0.001, 1.0),
    "SZ_A_STOCK": (0.01, 0.01),
    "SZ_B_STOCK": (0.01, 0.01),
    "SZ_INDEX": (0.01, 1.0),
    "SZ_FUND": (0.001, 0.01),
    "SZ_BOND": (0.001, 0.01),
}


def _detect_security_type(filename: str) -> str:
    """从文件名推断证券类型。

    文件名格式: {exchange}{code}.day，如 sh600000.day、sz000001.day
    """
    base = Path(filename).name.lower()
    exchange = base[:2]  # "sh" or "sz"
    code_head = base[2:4]

    if exchange == "sz":
        if code_head in ("00", "30"):
            return "SZ_A_STOCK"
        if code_head == "20":
            return "SZ_B_STOCK"
        if code_head == "39":
            return "SZ_INDEX"
        if code_head in ("15", "16", "18"):
            return "SZ_FUND"
        if code_head in ("10", "11", "12", "13", "14"):
            return "SZ_BOND"
    elif exchange == "sh":
        if code_head == "60":
            return "SH_A_STOCK"
        if code_head == "90":
            return "SH_B_STOCK"
        if code_head == "68":
            return "SH_STAR_STOCK"
        if code_head in ("00", "88", "99"):
            return "SH_INDEX"
        if code_head in ("50", "51", "58"):
            return "SH_FUND"
        if code_head in (
            "01",
            "02",
            "10",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "17",
            "18",
            "19",
            "20",
        ):
            return "SH_BOND"

    return "SZ_A_STOCK"  # 默认按 A 股处理


def _decode_daily(data: bytes) -> np.ndarray:
    """将整个 .day 文件向量化解析为结构化数组（仅完整记录）。"""
    n = len(data) // _DAILY_DTYPE.itemsize
    return np.frombuffer(data, dtype=_DAILY_DTYPE, count=n)


def read_daily_bars(filepath: str | Path) -> list[SecurityBar]:
    """从本地 .day 文件读取日线 K 线数据。

    Args:
        filepath: .day 文件路径。

    Returns:
        SecurityBar 列表（按时间升序）。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"日线数据文件不存在: {filepath}")

    sec_type = _detect_security_type(filepath.name)
    price_coeff, vol_coeff = _SECURITY_COEFFICIENTS.get(sec_type, (0.01, 0.01))

    data = filepath.read_bytes()
    if len(data) < _DAILY_FMT.size:
        return []

    arr = _decode_daily(data)
    size = _DAILY_DTYPE.itemsize
    date = arr["date"]
    year = (date // 10000).astype(int)
    month = ((date % 10000) // 100).astype(int)
    day = (date % 100).astype(int)
    open_ = arr["open"].astype(float) * price_coeff
    close = arr["close"].astype(float) * price_coeff
    high = arr["high"].astype(float) * price_coeff
    low = arr["low"].astype(float) * price_coeff
    vol = arr["vol"].astype(float) * vol_coeff
    amount = arr["amount"].astype(float)

    return [
        SecurityBar(
            open=float(open_[i]),
            close=float(close[i]),
            high=float(high[i]),
            low=float(low[i]),
            vol=float(vol[i]),
            amount=float(amount[i]),
            year=int(year[i]),
            month=int(month[i]),
            day=int(day[i]),
            hour=0,
            minute=0,
            _raw=data[i * size : (i + 1) * size],
        )
        for i in range(len(arr))
    ]


def read_daily_bars_df(filepath: str | Path) -> pd.DataFrame:
    """向量化读取 .day 为 DataFrame（跳过逐条 dataclass，最快路径）。

    列：date, open, close, high, low, vol, amount（按时间升序）。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"日线数据文件不存在: {filepath}")
    sec_type = _detect_security_type(filepath.name)
    price_coeff, vol_coeff = _SECURITY_COEFFICIENTS.get(sec_type, (0.01, 0.01))
    data = filepath.read_bytes()
    if len(data) < _DAILY_FMT.size:
        return pd.DataFrame(columns=["date", "open", "close", "high", "low", "vol", "amount"])
    arr = _decode_daily(data)
    date = arr["date"]
    return pd.DataFrame(
        {
            "date": pd.to_datetime(date.astype("U8"), format="%Y%m%d"),
            "open": arr["open"].astype(float) * price_coeff,
            "close": arr["close"].astype(float) * price_coeff,
            "high": arr["high"].astype(float) * price_coeff,
            "low": arr["low"].astype(float) * price_coeff,
            "vol": arr["vol"].astype(float) * vol_coeff,
            "amount": arr["amount"].astype(float),
        }
    )


def find_daily_bar_file(
    market: int,
    code: str,
    vipdoc: str | Path | None = None,
) -> Path:
    """根据市场和代码定位日线文件路径。

    Args:
        market: 市场代码（Market.SZ=0, Market.SH=1）。
        code: 6 位股票代码。
        vipdoc: vipdoc 目录路径，None 则自动检测。

    Returns:
        .day 文件的 Path。
    """
    vipdoc_path = resolve_vipdoc(vipdoc)
    exchange = _market_to_exchange(market)
    return vipdoc_path / exchange / "lday" / f"{exchange}{code}.day"
