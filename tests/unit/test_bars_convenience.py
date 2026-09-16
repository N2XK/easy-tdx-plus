"""K 线便利方法测试：自动路由 / 日期区间分页 / 市场推断（离线，无需网络）。"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from easy_tdx import AsyncTdxClient, KlineCategory, Market, TdxClient
from easy_tdx.client import _infer_market, _looks_like_index, _validate_yyyymmdd


def _page(dates: list[int], close: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime([str(d) for d in dates]),
            "open": close,
            "close": close,
            "high": close,
            "low": close,
            "vol": 1.0,
            "amount": 1.0,
        }
    )


def _days(df: pd.DataFrame) -> list[int]:
    return pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype(int).tolist()


def _client() -> TdxClient:
    return TdxClient(host="127.0.0.1")  # 不建立连接，仅调用纯逻辑方法


def _paged_get_bars(pages: dict[int, pd.DataFrame]):
    """构造按 start 返回预设页的 get_bars 桩函数。"""

    def fake(
        m: Market, code: str, cat: KlineCategory, start: int, count: int = 800
    ) -> pd.DataFrame:
        return pages.get(start, _page([]))

    return fake


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #


def test_looks_like_index() -> None:
    assert _looks_like_index(Market.SH, "000001")
    assert _looks_like_index(Market.SH, "880646")
    assert _looks_like_index(Market.SZ, "399001")
    assert not _looks_like_index(Market.SH, "600519")
    assert not _looks_like_index(Market.SZ, "000001")
    assert not _looks_like_index(Market.BJ, "430047")


def test_infer_market() -> None:
    assert _infer_market("600519") == Market.SH
    assert _infer_market("510300") == Market.SH
    assert _infer_market("900901") == Market.SH
    assert _infer_market("000001") == Market.SZ
    assert _infer_market("300750") == Market.SZ


def test_validate_yyyymmdd() -> None:
    _validate_yyyymmdd(20260915, "start_date")  # 不抛异常
    _validate_yyyymmdd("20260915", "start_date")  # 数字字符串按内容校验，同样接受
    for bad in (2026091, 202609151, 2026.1, -20260915, "2026-09-15"):
        with pytest.raises(ValueError):
            _validate_yyyymmdd(bad, "start_date")  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# get_bars 路由
# --------------------------------------------------------------------------- #


def test_get_bars_routes_index(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    calls: list[str] = []
    monkeypatch.setattr(
        c, "get_index_bars", lambda *a, **k: calls.append("index") or _page([20260915])
    )
    monkeypatch.setattr(
        c, "get_security_bars", lambda *a, **k: calls.append("stock") or _page([20260915])
    )
    c.get_bars(Market.SH, "000001", KlineCategory.DAY, 0, 5)
    assert calls == ["index"]


def test_get_bars_routes_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    calls: list[str] = []
    monkeypatch.setattr(
        c, "get_index_bars", lambda *a, **k: calls.append("index") or _page([20260915])
    )
    monkeypatch.setattr(
        c, "get_security_bars", lambda *a, **k: calls.append("stock") or _page([20260915])
    )
    c.get_bars(Market.SZ, "000001", KlineCategory.DAY, 0, 5)
    assert calls == ["stock"]


# --------------------------------------------------------------------------- #
# get_bars_range
# --------------------------------------------------------------------------- #


def test_get_bars_range_paginates_filters_sorts(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    pages = {
        0: _page([20260915, 20260914, 20260913]),
        3: _page([20260912, 20260911, 20260910]),
    }
    monkeypatch.setattr(c, "get_bars", _paged_get_bars(pages))

    res = c.get_bars_range(Market.SH, "600519", 20260910, 20260913, KlineCategory.DAY, count=3)
    assert _days(res) == [20260910, 20260911, 20260912, 20260913]


def test_get_bars_range_stops_on_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    calls: list[int] = []

    def fake(
        m: Market, code: str, cat: KlineCategory, start: int, count: int = 800
    ) -> pd.DataFrame:
        calls.append(start)
        return _page([20260915, 20260914])  # 少于 count -> 应停止

    monkeypatch.setattr(c, "get_bars", fake)
    res = c.get_bars_range(Market.SH, "600519", 20260101, 20260915, KlineCategory.DAY, count=10)
    assert calls == [0]
    assert len(res) == 2


def test_get_bars_range_dedups_overlapping_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    pages = {
        0: _page([20260915, 20260914, 20260913]),
        3: _page([20260913, 20260912, 20260911]),
    }
    monkeypatch.setattr(c, "get_bars", _paged_get_bars(pages))
    res = c.get_bars_range(Market.SH, "600519", 20260911, 20260915, KlineCategory.DAY, count=3)
    assert _days(res) == [20260911, 20260912, 20260913, 20260914, 20260915]


def test_get_bars_range_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    monkeypatch.setattr(c, "get_bars", lambda *a, **k: _page([]))
    res = c.get_bars_range(Market.SH, "600519", 20270101, 20271231, KlineCategory.DAY, count=3)
    assert res.empty


def test_get_bars_range_invalid_range() -> None:
    c = _client()
    with pytest.raises(ValueError):
        c.get_bars_range(Market.SH, "600519", 20260915, 20260901)
    with pytest.raises(ValueError):
        c.get_bars_range(Market.SH, "600519", 2026091, 20260915)


# --------------------------------------------------------------------------- #
# get_k_data 市场推断
# --------------------------------------------------------------------------- #


def test_get_k_data_infers_market(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    seen: dict[str, Market] = {}

    def fake(
        market: Market,
        code: str,
        start: int,
        end: int,
        category: KlineCategory = KlineCategory.DAY,
    ) -> pd.DataFrame:
        seen[code] = market
        return _page([end])

    monkeypatch.setattr(c, "get_bars_range", fake)
    c.get_k_data("600519", 20260901, 20260915)
    c.get_k_data("000001", 20260901, 20260915)
    assert seen == {"600519": Market.SH, "000001": Market.SZ}


# --------------------------------------------------------------------------- #
# 异步
# --------------------------------------------------------------------------- #


def test_async_get_bars_range() -> None:
    async def main() -> pd.DataFrame:
        c = AsyncTdxClient(host="127.0.0.1")

        async def fake_get_bars(
            m: Market, code: str, cat: KlineCategory, start: int, count: int = 800
        ) -> pd.DataFrame:
            if start == 0:
                return _page([20260915, 20260914, 20260913])
            return _page([])

        c.get_bars = fake_get_bars  # type: ignore[method-assign]
        return await c.get_bars_range(Market.SH, "600519", 20260901, 20260915, count=3)

    res = asyncio.run(main())
    assert _days(res) == [20260913, 20260914, 20260915]


def test_get_recent_minute_time_data(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1")
    monkeypatch.setattr(
        c,
        "get_bars",
        lambda *a, **k: pd.DataFrame(
            {"date": pd.to_datetime(["2026-09-11", "2026-09-14", "2026-09-15"])}
        ),
    )
    calls: list[int] = []

    def fake_hist(market: Market, code: str, date: int) -> pd.DataFrame:
        calls.append(date)
        return pd.DataFrame({"datetime": pd.to_datetime([f"{date} 09:30"]), "price": [1.0]})

    monkeypatch.setattr(c, "get_history_minute_time_data", fake_hist)
    df = c.get_recent_minute_time_data(Market.SH, "600519", days=3)
    assert calls == [20260911, 20260914, 20260915]  # 升序
    assert len(df) == 3


def test_get_recent_minute_time_data_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1")
    monkeypatch.setattr(c, "get_bars", lambda *a, **k: pd.DataFrame())
    assert c.get_recent_minute_time_data(Market.SH, "600519").empty


def _txn(dts: list[str], vol: int = 1) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": pd.to_datetime(dts),
            "price": 9.0,
            "vol": vol,
            "buyorsell": 1,
            "unknown_last": 0,
        }
    )


def test_get_history_transaction_all_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    pages = {
        0: _txn([f"2024-01-02 14:{i:02d}" for i in range(10, 0, -1)]),
        10: _txn(["2024-01-02 09:31", "2024-01-02 09:30"]),
    }

    def fake(market: Market, code: str, date: int, start: int, count: int = 800) -> pd.DataFrame:
        return pages.get(start, _txn([]))

    monkeypatch.setattr(c, "get_history_transaction_data", fake)
    df = c.get_history_transaction_all(Market.SZ, "000001", 20240102, count=10)
    assert len(df) == 12
    assert df["datetime"].is_monotonic_increasing
    assert df["datetime"].iloc[0] == pd.Timestamp("2024-01-02 09:30")


def test_get_history_transaction_all_keeps_identical_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _client()
    calls: list[int] = []

    def fake(market: Market, code: str, date: int, start: int, count: int = 800) -> pd.DataFrame:
        calls.append(start)
        return _txn(["2024-01-02 09:30"] * 2, vol=5) if start == 0 else _txn([])

    monkeypatch.setattr(c, "get_history_transaction_data", fake)
    df = c.get_history_transaction_all(Market.SZ, "000001", 20240102, count=2)
    assert len(df) == 2
    assert calls == [0, 2]


def test_get_history_transaction_all_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    monkeypatch.setattr(c, "get_history_transaction_data", lambda *a, **k: pd.DataFrame())
    assert c.get_history_transaction_all(Market.SZ, "000001", 20240102).empty


def test_async_get_history_transaction_all_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    c = AsyncTdxClient(host="127.0.0.1")

    async def fake(
        market: Market, code: str, date: int, start: int, count: int = 800
    ) -> pd.DataFrame:
        if start == 0:
            return _txn([f"2024-01-02 14:{i:02d}" for i in range(10, 0, -1)])
        return _txn([])

    monkeypatch.setattr(c, "get_history_transaction_data", fake)
    df = asyncio.run(c.get_history_transaction_all(Market.SZ, "000001", 20240102, count=10))
    assert len(df) == 10
    assert df["datetime"].is_monotonic_increasing


def test_paginate_helper() -> None:
    from easy_tdx.client import _paginate

    pages = {0: pd.DataFrame({"a": [1, 2]}), 2: pd.DataFrame({"a": [3]})}

    def fetch(start: int, count: int) -> pd.DataFrame:
        return pages.get(start, pd.DataFrame({"a": []}))

    out = _paginate(fetch, 2)
    assert out["a"].tolist() == [1, 2, 3]
    assert _paginate(lambda s, c: pd.DataFrame({"a": []}), 2).empty


def test_paginate_async_helper() -> None:
    from easy_tdx.client import _paginate_async

    pages = {0: pd.DataFrame({"a": [1, 2]}), 2: pd.DataFrame({"a": [3]})}

    async def fetch(start: int, count: int) -> pd.DataFrame:
        return pages.get(start, pd.DataFrame({"a": []}))

    out = asyncio.run(_paginate_async(fetch, 2))
    assert out["a"].tolist() == [1, 2, 3]


def test_get_security_features_all_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _client()
    calls: list[int] = []

    def fake(start: int, count: int = 2000) -> pd.DataFrame:
        calls.append(start)
        if start == 0:
            return pd.DataFrame({"code": [f"{i:06d}" for i in range(count)]})
        return pd.DataFrame({"code": ["000001"]})

    monkeypatch.setattr(c, "get_security_features", fake)
    df = c.get_security_features_all(count=2000)
    assert calls == [0, 2000]
    assert len(df) == 2001
