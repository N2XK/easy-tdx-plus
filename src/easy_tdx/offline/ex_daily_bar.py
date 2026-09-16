"""扩展市场日线数据读取（期货、港股等 .day 文件）。"""

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..exceptions import TdxFileNotFoundError

# 日期(4B) 开盘(4Bf) 最高(4Bf) 最低(4Bf) 收盘(4Bf) 成交额(4B) 成交量(4B) 结算价(4Bf)
_EX_DAILY_FMT = struct.Struct("<IffffIIf")

_EX_DAILY_DTYPE = np.dtype(
    [
        ("date", "<u4"),
        ("open", "<f4"),
        ("high", "<f4"),
        ("low", "<f4"),
        ("close", "<f4"),
        ("amt_u", "<u4"),
        ("vol", "<u4"),
        ("settlement", "<f4"),
    ]
)


@dataclass
class ExDailyBar:
    """扩展市场日线（期货/港股等，含结算价）。"""

    open: float
    high: float
    low: float
    close: float
    amount: int
    vol: int
    settlement: float
    hk_stock_amount: float
    year: int
    month: int
    day: int
    _raw: bytes = field(default=b"", repr=False, compare=False)


def read_ex_daily_bars(filepath: str | Path) -> list[ExDailyBar]:
    """从本地扩展市场 .day 文件读取日线数据。

    文件位于 vipdoc/ds/ 目录下，如 29#A1801.day。

    Args:
        filepath: .day 文件路径。

    Returns:
        ExDailyBar 列表（按时间升序）。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"扩展市场日线文件不存在: {filepath}")

    data = filepath.read_bytes()
    if len(data) < _EX_DAILY_FMT.size:
        return []

    size = _EX_DAILY_DTYPE.itemsize
    arr = np.frombuffer(data, dtype=_EX_DAILY_DTYPE, count=len(data) // size)
    date = arr["date"]
    year = (date // 10000).astype(int)
    month = ((date % 10000) // 100).astype(int)
    day = (date % 100).astype(int)
    hk = arr["amt_u"].copy().view("<f4")  # 成交额位置按 float 重解释
    return [
        ExDailyBar(
            open=float(arr["open"][i]),
            high=float(arr["high"][i]),
            low=float(arr["low"][i]),
            close=float(arr["close"][i]),
            amount=int(arr["amt_u"][i]),
            vol=int(arr["vol"][i]),
            settlement=float(arr["settlement"][i]),
            hk_stock_amount=float(hk[i]),
            year=int(year[i]),
            month=int(month[i]),
            day=int(day[i]),
            _raw=data[i * size : (i + 1) * size],
        )
        for i in range(len(arr))
    ]


def read_ex_daily_bars_df(filepath: str | Path) -> pd.DataFrame:
    """向量化读取扩展市场 .day 为 DataFrame。"""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"扩展市场日线文件不存在: {filepath}")
    data = filepath.read_bytes()
    cols = ["date", "open", "close", "high", "low", "vol", "amount", "settlement"]
    if len(data) < _EX_DAILY_FMT.size:
        return pd.DataFrame(columns=cols)
    arr = np.frombuffer(data, dtype=_EX_DAILY_DTYPE, count=len(data) // _EX_DAILY_DTYPE.itemsize)
    return pd.DataFrame(
        {
            "date": pd.to_datetime(arr["date"].astype("U8"), format="%Y%m%d"),
            "open": arr["open"].astype(float),
            "close": arr["close"].astype(float),
            "high": arr["high"].astype(float),
            "low": arr["low"].astype(float),
            "vol": arr["vol"].astype(float),
            "amount": arr["amt_u"].astype(float),
            "settlement": arr["settlement"].astype(float),
            "hk_stock_amount": arr["amt_u"].copy().view("<f4").astype(float),
        }
    )
