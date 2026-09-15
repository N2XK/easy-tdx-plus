"""离线解析向量化测试（离线，合成二进制文件）。"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from easy_tdx.offline import (
    read_5min_bars,
    read_5min_bars_df,
    read_daily_bars,
    read_daily_bars_df,
    read_ex_daily_bars,
    read_ex_daily_bars_df,
    read_lc_min_bars,
    read_lc_min_bars_df,
)

_DAILY_FMT = struct.Struct("<IIIIIfII")
_MIN_FMT = struct.Struct("<HHIIIIfII")
_LC_FMT = struct.Struct("<HHfffffII")
_EX_FMT = struct.Struct("<IffffIIf")


def _tdx_date(year: int, month: int, day: int) -> int:
    return (year - 2004) * 2048 + month * 100 + day


def test_daily_vectorized(tmp_path: Path) -> None:
    body = b"".join(
        [
            _DAILY_FMT.pack(20260915, 1000, 1010, 990, 1005, 12345.0, 500, 0),
            _DAILY_FMT.pack(20260916, 1010, 1020, 1000, 1015, 23456.0, 600, 0),
        ]
    )
    path = tmp_path / "sh600519.day"
    path.write_bytes(body)

    bars = read_daily_bars(path)
    assert len(bars) == 2
    assert (bars[0].year, bars[0].month, bars[0].day) == (2026, 9, 15)
    assert bars[0].open == pytest.approx(10.0)  # 1000 * 0.01
    assert bars[0].close == pytest.approx(10.05)
    assert bars[0].vol == pytest.approx(5.0)  # 500 * 0.01（A股量系数）
    assert bars[1].high == pytest.approx(10.2)

    df = read_daily_bars_df(path)
    assert list(df.columns) == ["date", "open", "close", "high", "low", "vol", "amount"]
    assert str(df["date"].iloc[0])[:10] == "2026-09-15"
    assert df["open"].tolist() == pytest.approx([10.0, 10.1])
    assert df["vol"].tolist() == pytest.approx([5.0, 6.0])


def test_5min_vectorized(tmp_path: Path) -> None:
    body = _MIN_FMT.pack(_tdx_date(2026, 9, 15), 9 * 60 + 35, 1000, 1010, 990, 1005, 123.0, 500, 0)
    path = tmp_path / "sh600519.5"
    path.write_bytes(body)

    bars = read_5min_bars(path)
    assert len(bars) == 1
    b = bars[0]
    assert (b.year, b.month, b.day, b.hour, b.minute) == (2026, 9, 15, 9, 35)
    assert b.open == pytest.approx(10.0)

    df = read_5min_bars_df(path)
    assert list(df.columns) == ["datetime", "open", "close", "high", "low", "vol", "amount"]
    assert str(df["datetime"].iloc[0]) == "2026-09-15 09:35:00"


def test_lc_min_vectorized(tmp_path: Path) -> None:
    body = _LC_FMT.pack(_tdx_date(2026, 9, 15), 13 * 60 + 5, 10.5, 10.6, 10.4, 10.55, 123.0, 500, 0)
    path = tmp_path / "sh600519.lc5"
    path.write_bytes(body)

    bars = read_lc_min_bars(path)
    assert len(bars) == 1
    assert bars[0].open == pytest.approx(10.5)
    assert (bars[0].hour, bars[0].minute) == (13, 5)

    df = read_lc_min_bars_df(path)
    assert df["close"].iloc[0] == pytest.approx(10.55)


def test_ex_daily_vectorized(tmp_path: Path) -> None:
    hk = 1.25
    amt_u = struct.unpack("<I", struct.pack("<f", hk))[0]
    body = _EX_FMT.pack(20260915, 10.5, 10.6, 10.4, 10.55, amt_u, 500, 10.52)
    path = tmp_path / "A1801.day"
    path.write_bytes(body)

    bars = read_ex_daily_bars(path)
    assert len(bars) == 1
    assert bars[0].open == pytest.approx(10.5)
    assert bars[0].vol == 500
    assert bars[0].hk_stock_amount == pytest.approx(1.25)

    df = read_ex_daily_bars_df(path)
    assert df["settlement"].iloc[0] == pytest.approx(10.52)
    assert df["hk_stock_amount"].iloc[0] == pytest.approx(1.25)


def test_truncated_file_ignored(tmp_path: Path) -> None:
    # 一条完整 + 半条：只解析完整记录
    body = _DAILY_FMT.pack(20260915, 1000, 1010, 990, 1005, 12345.0, 500, 0) + b"\x00" * 10
    path = tmp_path / "sh600519.day"
    path.write_bytes(body)
    assert len(read_daily_bars(path)) == 1
    assert len(read_daily_bars_df(path)) == 1


def test_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "sh600519.day"
    path.write_bytes(b"")
    assert read_daily_bars(path) == []
    assert read_daily_bars_df(path).empty
