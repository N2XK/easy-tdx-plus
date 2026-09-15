"""并发连接池与批量下载器测试（离线，使用假客户端）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from easy_tdx.downloader import Downloader
from easy_tdx.models.enums import KlineCategory, Market
from easy_tdx.parallel import ParallelTdx


class _FakeClient:
    def __init__(self) -> None:
        self.connected = False
        self.closed = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.closed = True


def test_parallel_map_preserves_order() -> None:
    created: list[_FakeClient] = []

    def factory() -> _FakeClient:
        c = _FakeClient()
        created.append(c)
        return c

    with ParallelTdx(connections=3, client_factory=factory) as pool:
        assert len(created) == 3
        assert all(c.connected for c in created)
        result = pool.map(lambda c, x: x * 2, [1, 2, 3, 4, 5])
    assert result == [2, 4, 6, 8, 10]
    assert all(c.closed for c in created)


def _bars(date_int: int) -> pd.DataFrame:
    d = pd.Timestamp(str(date_int))
    return pd.DataFrame(
        {
            "date": [d],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "vol": [1.0],
            "amount": [1.0],
        }
    )


class _DownloadFakeClient(_FakeClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[int] = []

    def get_bars_range(
        self, market: Market, code: str, begin: int, end: int, category: KlineCategory
    ) -> pd.DataFrame:
        self.calls.append(begin)
        if begin > end:
            return pd.DataFrame()
        return _bars(begin)


def test_downloader_incremental(tmp_path: Path) -> None:
    clients: list[_DownloadFakeClient] = []

    def factory() -> _DownloadFakeClient:
        c = _DownloadFakeClient()
        clients.append(c)
        return c

    dl = Downloader(tmp_path, connections=1, client_factory=factory, end_date=20991231)
    stocks = [(Market.SH, "600519")]

    r1 = dl.download_daily(stocks, start_date=20260101, fmt="csv")
    assert r1["sh600519"] == 1
    assert clients[0].calls == [20260101]

    # 第二次应从 next_day(20260101) 开始（增量），并去重
    r2 = dl.download_daily(stocks, start_date=20260101, fmt="csv")
    assert r2["sh600519"] == 1
    assert clients[1].calls == [20260102]

    saved = pd.read_csv(tmp_path / "sh600519.csv")
    assert len(saved) == 2
    assert saved["date"].nunique() == 2


def test_downloader_skips_up_to_date(tmp_path: Path) -> None:
    clients: list[_DownloadFakeClient] = []

    def factory() -> _DownloadFakeClient:
        c = _DownloadFakeClient()
        clients.append(c)
        return c

    dl = Downloader(tmp_path, connections=1, client_factory=factory, end_date=20260101)
    stocks = [(Market.SH, "600519")]
    dl.download_daily(stocks, start_date=20260101, fmt="csv")
    # manifest 已是 20260101，end=20260101 -> begin=20260102 > end -> 跳过
    r2 = dl.download_daily(stocks, start_date=20260101, fmt="csv")
    assert r2["sh600519"] == 0
    assert clients[-1].calls == []
