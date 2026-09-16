"""统一客户端的"MAC 优先 / 标准兜底"路由测试（离线，注入假客户端）。"""

from __future__ import annotations

import asyncio

import pandas as pd
import pytest

from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.unified import AsyncUnifiedTdxClient, UnifiedTdxClient


def _df(tag: str) -> pd.DataFrame:
    return pd.DataFrame({"src": [tag]})


class _FakeMac:
    def __init__(self, *, kind: str = "ok") -> None:
        self.kind = kind
        self.calls: list[str] = []

    def get_stock_quotes(self, stocks: object, fields: object = None) -> pd.DataFrame:
        self.calls.append("quotes")
        if self.kind == "err":
            raise TdxConnectionError("mac down")
        if self.kind == "empty":
            return pd.DataFrame()
        return _df("mac")

    def get_transactions(
        self, market: int, code: str, count: int = 0, start: int = 0, date: int | None = None
    ) -> pd.DataFrame:
        self.calls.append(f"txn:{date}")
        if self.kind == "err":
            raise TdxConnectionError("mac down")
        if self.kind == "empty":
            return pd.DataFrame()
        return _df("mac")

    def get_stock_kline(
        self,
        market: int,
        code: str,
        period: object,
        start: int = 0,
        count: int = 800,
        times: int = 1,
        adjust: object = None,
    ) -> pd.DataFrame:
        if self.kind == "err":
            raise TdxConnectionError("mac down")
        if self.kind == "empty":
            return pd.DataFrame()
        return _df("mac")

    def close(self) -> None:
        pass


class _FakeStd:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_security_quotes(self, stocks: object) -> pd.DataFrame:
        self.calls.append("quotes")
        return _df("std")

    def get_bars(
        self, market: object, code: str, category: object, start: int, count: int
    ) -> pd.DataFrame:
        self.calls.append(f"bars:{category}")
        return _df("std")

    def get_transaction_data(
        self, market: object, code: str, start: int, count: int
    ) -> pd.DataFrame:
        self.calls.append("txn_today")
        return _df("std")

    def get_history_transaction_data(
        self, market: object, code: str, date: int, start: int, count: int
    ) -> pd.DataFrame:
        self.calls.append(f"txn_hist:{date}")
        return _df("std")

    def close(self) -> None:
        pass


def _client(kind: str, *, fallback: bool = True) -> tuple[UnifiedTdxClient, _FakeMac, _FakeStd]:
    c = UnifiedTdxClient(fallback_std=fallback)
    mac, std = _FakeMac(kind=kind), _FakeStd()
    c._mac, c._std = mac, std  # type: ignore[assignment]
    return c, mac, std


def test_mac_preferred_when_ok() -> None:
    c, mac, std = _client("ok")
    df = c.get_stock_quotes([(1, "600519")])
    assert df.iloc[0]["src"] == "mac"
    assert std.calls == []  # 未触碰标准协议


@pytest.mark.parametrize("kind", ["err", "empty"])
def test_fallback_to_std(kind: str) -> None:
    c, _mac, std = _client(kind)
    assert c.get_stock_quotes([(1, "600519")]).iloc[0]["src"] == "std"
    assert std.calls == ["quotes"]


def test_transactions_date_routing() -> None:
    c, _mac, std = _client("empty")
    c.get_transactions(0, "000001", date=None)
    c.get_transactions(0, "000001", date=20240102)
    assert std.calls == ["txn_today", "txn_hist:20240102"]


def test_fallback_disabled_raises() -> None:
    c, _mac, _std = _client("err", fallback=False)
    with pytest.raises(TdxConnectionError):
        c.get_stock_quotes([(1, "600519")])


def test_fallback_disabled_empty_returns_empty() -> None:
    c, _mac, std = _client("empty", fallback=False)
    assert c.get_stock_quotes([(1, "600519")]).empty
    assert std.calls == []


def test_kline_fallback_maps_category() -> None:
    from easy_tdx.mac.enums import Period
    from easy_tdx.models.enums import KlineCategory

    c, _mac, std = _client("err")
    df = c.get_stock_kline(0, "000001", Period.DAILY, count=10)
    assert df.iloc[0]["src"] == "std"
    assert std.calls == [f"bars:{KlineCategory.DAY}"]


def test_kline_fallback_skips_unsupported_period() -> None:
    from easy_tdx.mac.enums import Period

    c, _mac, std = _client("err")
    # Period.DAYS（多日）无标准协议等价 → 不回退、返回空
    assert c.get_stock_kline(0, "000001", Period.DAYS, count=10).empty
    assert std.calls == []


class _AsyncFakeMac(_FakeMac):
    async def get_stock_quotes(self, stocks: object, fields: object = None) -> pd.DataFrame:
        return super().get_stock_quotes(stocks, fields)

    async def get_transactions(
        self, market: int, code: str, count: int = 0, start: int = 0, date: int | None = None
    ) -> pd.DataFrame:
        return super().get_transactions(market, code, count, start, date)


class _AsyncFakeStd(_FakeStd):
    async def get_security_quotes(self, stocks: object) -> pd.DataFrame:
        return super().get_security_quotes(stocks)

    async def get_transaction_data(
        self, market: object, code: str, start: int, count: int
    ) -> pd.DataFrame:
        return super().get_transaction_data(market, code, start, count)

    async def get_history_transaction_data(
        self, market: object, code: str, date: int, start: int, count: int
    ) -> pd.DataFrame:
        return super().get_history_transaction_data(market, code, date, start, count)


def test_async_fallback_to_std() -> None:
    c = AsyncUnifiedTdxClient()
    c._mac = _AsyncFakeMac(kind="err")  # type: ignore[assignment]
    c._std = _AsyncFakeStd()  # type: ignore[assignment]

    async def main() -> tuple[str, str]:
        q = await c.get_stock_quotes([(1, "600519")])
        t = await c.get_transactions(0, "000001", date=20240102)
        return q.iloc[0]["src"], t.iloc[0]["src"]

    assert asyncio.run(main()) == ("std", "std")
