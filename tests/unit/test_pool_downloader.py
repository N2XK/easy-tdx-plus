"""并发连接池与批量下载器测试（离线，使用假客户端）。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.downloader import Downloader
from easy_tdx.exceptions import TdxConnectionError
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


def test_parallel_recreates_on_connection_error() -> None:
    created: list[_FakeClient] = []

    def factory() -> _FakeClient:
        c = _FakeClient()
        created.append(c)
        return c

    attempts: dict[int, int] = {}

    def flaky(client: _FakeClient, item: int) -> int:
        attempts[item] = attempts.get(item, 0) + 1
        if attempts[item] == 1:
            raise TdxConnectionError("boom")
        return item

    with ParallelTdx(connections=1, client_factory=factory) as pool:
        result = pool.map(flaky, [1, 2])
    assert result == [1, 2]
    # 初始 1 个 + 每个 item 首次失败各重建 1 个
    assert len(created) == 3


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


def test_downloader_parquet_requires_pyarrow(tmp_path: Path) -> None:
    import importlib.util

    if importlib.util.find_spec("pyarrow") or importlib.util.find_spec("fastparquet"):
        pytest.skip("pyarrow/fastparquet 已安装")
    dl = Downloader(tmp_path, connections=1, client_factory=_DownloadFakeClient, end_date=20991231)
    with pytest.raises(ValueError, match="parquet"):
        dl.download_daily([(Market.SH, "600519")], fmt="parquet")


class _BadBarsClient(_FakeClient):
    def get_bars_range(
        self, market: Market, code: str, begin: int, end: int, category: KlineCategory
    ) -> pd.DataFrame:
        df = _bars(begin)
        df.loc[0, "high"] = -1.0  # 非法：high < open/close/low
        return df


def test_downloader_validate_skips_bad(tmp_path: Path) -> None:
    dl = Downloader(
        tmp_path,
        connections=1,
        client_factory=_BadBarsClient,
        end_date=20991231,
        validate=True,
    )
    r = dl.download_daily([(Market.SH, "600519")], start_date=20260101, fmt="csv")
    assert r["sh600519"] == 0
    assert "sh600519" in dl.errors
    assert not (tmp_path / "sh600519.csv").exists()
    assert dl._load_manifest().get("sh600519") is None


def test_downloader_new_data_wins_on_duplicate(tmp_path: Path) -> None:
    dl = Downloader(tmp_path, connections=1, client_factory=_FakeClient)
    a = _bars(20260101)
    a.loc[0, "close"] = 1.0
    dl._append("sh600519", a, "csv")
    b = _bars(20260101)
    b.loc[0, "close"] = 9.0
    dl._append("sh600519", b, "csv")  # 同键应以新数据为准
    saved = pd.read_csv(tmp_path / "sh600519.csv")
    assert len(saved) == 1
    assert saved.iloc[0]["close"] == 9.0


def test_verify_coverage_reports_gap(tmp_path: Path) -> None:
    dl = Downloader(
        tmp_path, connections=1, client_factory=_DownloadFakeClient, end_date=20260103
    )
    stocks = [(Market.SH, "600519")]
    dl.download_daily(stocks, start_date=20260101, fmt="csv")  # 假客户端只回 0101
    rep = dl.verify_coverage(stocks, trading_days=[20260101, 20260102, 20260103])
    row = rep.iloc[0]
    assert row["rows"] == 1
    assert row["covered_from"] == 20260101 and row["covered_to"] == 20260103
    assert row["expected"] == 3 and row["missing"] == 2
    assert row["missing_dates"] == [20260102, 20260103]


class _RangeFakeClient(_FakeClient):
    """按 [begin, end] 每个自然日返回一行。"""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[int, int]] = []

    def get_bars_range(
        self, market: Market, code: str, begin: int, end: int, category: KlineCategory
    ) -> pd.DataFrame:
        self.calls.append((begin, end))
        if begin > end:
            return pd.DataFrame()
        days = pd.date_range(str(begin), str(end), freq="D")
        frames = [_bars(int(x.strftime("%Y%m%d"))) for x in days]
        return pd.concat(frames, ignore_index=True)


def test_backfill_gaps_fills_missing(tmp_path: Path) -> None:
    clients: list[_RangeFakeClient] = []

    def factory() -> _RangeFakeClient:
        c = _RangeFakeClient()
        clients.append(c)
        return c

    dl = Downloader(tmp_path, connections=1, client_factory=factory, end_date=20260103)
    # 造一个"覆盖 [0101,0103] 但只有 0101"的状态
    dl._append("sh600519", _bars(20260101), "csv")
    dl._save_coverage({"sh600519": {"from": 20260101, "to": 20260103}})

    added = dl.backfill_gaps([(Market.SH, "600519")], trading_days=[20260101, 20260102, 20260103])
    assert added["sh600519"] == 2  # 0102、0103 补齐
    saved = pd.read_csv(tmp_path / "sh600519.csv")
    got = set(pd.to_datetime(saved["date"]).dt.strftime("%Y%m%d").astype(int))
    assert got == {20260101, 20260102, 20260103}
    # 缺口被归为一段请求
    assert clients[0].calls == [(20260102, 20260103)]
