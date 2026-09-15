"""分钟 K 线数据读取（.5 文件和 .lc1/.lc5 文件）。"""

import struct
from pathlib import Path

import numpy as np
import pandas as pd

from ..exceptions import TdxFileNotFoundError
from ..models.bar import SecurityBar

# .5 文件: 日期(2B) 时间(2B) 开盘(4B) 最高(4B) 最低(4B) 收盘(4B) 额(4B) 量(4B) 保留(4B)
_MIN_FMT = struct.Struct("<HHIIIIfII")

# .lc1/.lc5 文件: 日期(2B) 时间(2B) 开(4Bf) 高(4Bf) 低(4Bf) 收(4Bf) 额(4Bf) 量(4B) 保留(4B)
_LC_MIN_FMT = struct.Struct("<HHfffffII")

_MIN_DTYPE = np.dtype(
    [
        ("date", "<u2"),
        ("time", "<u2"),
        ("open", "<u4"),
        ("high", "<u4"),
        ("low", "<u4"),
        ("close", "<u4"),
        ("amount", "<f4"),
        ("vol", "<u4"),
        ("reserved", "<u4"),
    ]
)

_LC_MIN_DTYPE = np.dtype(
    [
        ("date", "<u2"),
        ("time", "<u2"),
        ("open", "<f4"),
        ("high", "<f4"),
        ("low", "<f4"),
        ("close", "<f4"),
        ("amount", "<f4"),
        ("vol", "<u4"),
        ("reserved", "<u4"),
    ]
)


def _decode_tdx_date(num: int) -> tuple[int, int, int]:
    """解码通达信压缩日期（2 字节）。"""
    year = num // 2048 + 2004
    month = (num % 2048) // 100
    day = (num % 2048) % 100
    return year, month, day


def _decode_tdx_time(num: int) -> tuple[int, int]:
    """解码通达信分钟时间（从 0:00 开始的分钟数）。"""
    return num // 60, num % 60


def _ymd(dates: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    base = dates % 2048
    return dates // 2048 + 2004, base // 100, base % 100


def _hm(times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return times // 60, times % 60


def _build_bars(arr: np.ndarray, data: bytes, price_div: float) -> list[SecurityBar]:
    size = arr.dtype.itemsize
    y, m, d = _ymd(arr["date"])
    hh, mm = _hm(arr["time"])
    open_ = arr["open"].astype(float) / price_div
    close = arr["close"].astype(float) / price_div
    high = arr["high"].astype(float) / price_div
    low = arr["low"].astype(float) / price_div
    vol = arr["vol"].astype(float)
    amount = arr["amount"].astype(float)
    return [
        SecurityBar(
            open=float(open_[i]),
            close=float(close[i]),
            high=float(high[i]),
            low=float(low[i]),
            vol=float(vol[i]),
            amount=float(amount[i]),
            year=int(y[i]),
            month=int(m[i]),
            day=int(d[i]),
            hour=int(hh[i]),
            minute=int(mm[i]),
            _raw=data[i * size : (i + 1) * size],
        )
        for i in range(len(arr))
    ]


def _build_df(arr: np.ndarray, price_div: float) -> pd.DataFrame:
    y, m, d = _ymd(arr["date"])
    hh, mm = _hm(arr["time"])
    dates = pd.to_datetime(
        {
            "year": y.astype("i4"),
            "month": m.astype("i4"),
            "day": d.astype("i4"),
            "hour": hh.astype("i4"),
            "minute": mm.astype("i4"),
        }
    )
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": arr["open"].astype(float) / price_div,
            "close": arr["close"].astype(float) / price_div,
            "high": arr["high"].astype(float) / price_div,
            "low": arr["low"].astype(float) / price_div,
            "vol": arr["vol"].astype(float),
            "amount": arr["amount"].astype(float),
        }
    )


def read_5min_bars(filepath: str | Path) -> list[SecurityBar]:
    """从本地 .5 文件读取 5 分钟 K 线数据。

    OHLC 为整数，需除以 100 得到实际价格。

    Args:
        filepath: .5 文件路径。

    Returns:
        SecurityBar 列表（按时间升序）。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"分钟线数据文件不存在: {filepath}")

    data = filepath.read_bytes()
    if len(data) < _MIN_FMT.size:
        return []

    arr = np.frombuffer(data, dtype=_MIN_DTYPE, count=len(data) // _MIN_DTYPE.itemsize)
    return _build_bars(arr, data, price_div=100.0)


def read_5min_bars_df(filepath: str | Path) -> pd.DataFrame:
    """向量化读取 .5 文件为 DataFrame（列：datetime, open, close, high, low, vol, amount）。"""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"分钟线数据文件不存在: {filepath}")
    data = filepath.read_bytes()
    if len(data) < _MIN_FMT.size:
        return pd.DataFrame(columns=["datetime", "open", "close", "high", "low", "vol", "amount"])
    arr = np.frombuffer(data, dtype=_MIN_DTYPE, count=len(data) // _MIN_DTYPE.itemsize)
    return _build_df(arr, price_div=100.0)


def read_lc_min_bars(filepath: str | Path) -> list[SecurityBar]:
    """从本地 .lc1/.lc5 文件读取分钟 K 线数据。

    OHLC 为 float 类型，无需额外转换。

    Args:
        filepath: .lc1 或 .lc5 文件路径。

    Returns:
        SecurityBar 列表（按时间升序）。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"分钟线数据文件不存在: {filepath}")

    data = filepath.read_bytes()
    if len(data) < _LC_MIN_FMT.size:
        return []

    arr = np.frombuffer(data, dtype=_LC_MIN_DTYPE, count=len(data) // _LC_MIN_DTYPE.itemsize)
    return _build_bars(arr, data, price_div=1.0)


def read_lc_min_bars_df(filepath: str | Path) -> pd.DataFrame:
    """向量化读取 .lc1/.lc5 为 DataFrame（列：datetime, open, close, high, low, vol, amount）。"""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"分钟线数据文件不存在: {filepath}")
    data = filepath.read_bytes()
    if len(data) < _LC_MIN_FMT.size:
        return pd.DataFrame(columns=["datetime", "open", "close", "high", "low", "vol", "amount"])
    arr = np.frombuffer(data, dtype=_LC_MIN_DTYPE, count=len(data) // _LC_MIN_DTYPE.itemsize)
    return _build_df(arr, price_div=1.0)
