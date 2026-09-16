"""真实服务器的「数据下载」集成测试（默认跳过）。

运行：``XMTDX_LIVE=1 python -m pytest tests/integration/test_live_download.py -v``

覆盖两条下载链路：
1. ``Downloader`` 日线批量下载（增量 + 覆盖度校验 + 缺口补拉）；
2. 官方站点直连下载（downit 清单 + ``download_channel``，含完整性校验）。
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx import Downloader, Market, TdxClient

_LIVE_ENABLED = os.getenv("XMTDX_LIVE") == "1"

pytestmark = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason="set XMTDX_LIVE=1 to run live integration tests",
)

_STOCKS = [(Market.SH, "600519"), (Market.SZ, "000001")]


def _rows(data_dir: Path, market: Market, code: str) -> int:
    path = data_dir / f"{market.name.lower()}{code}.csv"
    return len(pd.read_csv(path)) if path.exists() else 0


def test_live_downloader_incremental(tmp_path: Path) -> None:
    dl = Downloader(tmp_path, connections=2)
    r1 = dl.download_daily(_STOCKS, start_date=20250101, fmt="csv")
    assert all(n > 0 for n in r1.values()), r1
    assert dl.errors == {}
    first = {k: _rows(tmp_path, *s) for s, k in zip(_STOCKS, r1)}

    # 重复下载应为增量（不产生重复行）
    r2 = dl.download_daily(_STOCKS, start_date=20250101, fmt="csv")
    for stock, key in zip(_STOCKS, r1):
        assert _rows(tmp_path, *stock) == first[key], f"{key} 出现重复行，增量失效"
    assert all(n == 0 for n in r2.values()), f"重复下载仍新增数据: {r2}"

    # 落盘日期升序且唯一
    df = pd.read_csv(tmp_path / "sh600519.csv")
    assert df["date"].is_monotonic_increasing and df["date"].is_unique


def test_live_downloader_verify_and_backfill(tmp_path: Path) -> None:
    from datetime import date as _date
    from datetime import timedelta

    end = int(_date.today().strftime("%Y%m%d"))
    start = int((_date.today() - timedelta(days=180)).strftime("%Y%m%d"))

    dl = Downloader(tmp_path, connections=2)
    dl.download_daily(_STOCKS, start_date=start, fmt="csv")
    assert dl.errors == {}

    with TdxClient.from_best_host() as c:
        cal = c.get_trading_calendar(start, end) if hasattr(c, "get_trading_calendar") else None
    trading_days = cal.days if cal is not None else None

    rep = dl.verify_coverage(_STOCKS, trading_days=trading_days, fmt="csv")
    assert len(rep) == len(_STOCKS)
    assert set(rep.columns) >= {"key", "covered_from", "covered_to", "rows", "last_date"}
    if trading_days is not None:
        # 贵州茅台极少停牌：近半年缺口应为 0（允许个别节假日历误差）
        maotai = rep[rep["code"] == "600519"].iloc[0]
        assert maotai["missing"] is not None and maotai["missing"] <= 1, maotai.to_dict()

        added = dl.backfill_gaps(_STOCKS, trading_days=trading_days, fmt="csv")
        assert set(added) == {f"{m.name.lower()}{c}" for m, c in _STOCKS}
        assert all(n >= 0 for n in added.values())


def test_live_official_manifest_and_download(tmp_path: Path) -> None:
    from easy_tdx.offline import official

    channels = official.fetch_manifest()
    assert channels, "downit 清单为空"

    # 直连下载一个真实文件（dbf/gbbq.zip，约 6MB），校验完整性 + 无 .part 残留
    static = [ch for ch in channels if "YYYYMMDD" not in ch.file]
    assert static, "清单中没有固定文件名通道"
    target = next((ch for ch in static if ch.file.endswith(".zip")), static[0])
    dest = official.download_channel(target, tmp_path)
    assert dest.exists()
    assert dest.read_bytes()[:2] == b"PK"  # zip 魔数
    assert not dest.with_suffix(dest.suffix + ".part").exists()
