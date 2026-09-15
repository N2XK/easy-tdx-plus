"""7615 F10 / TQLEX 解析与客户端测试（离线）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from easy_tdx.f10 import F10Client, parse_tqlex_response, split_code

FIX = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIX / name).read_text("utf-8"))


class _FakeTransport:
    """记录调用并回放固定 JSON 的假传输层。"""

    def __init__(self, response: dict[str, Any]) -> None:
        self.base_url = "http://fake/TQLEX"
        self.timeout = 1.0
        self.retries = 0
        self.response = response
        self.calls: list[tuple[str, Any]] = []

    def post(self, entry: str, body: Any) -> dict[str, Any]:
        self.calls.append((entry, body))
        return self.response


def test_split_code() -> None:
    assert split_code("600519") == (1, "sh", "600519")
    assert split_code("sh600519") == (1, "sh", "600519")
    assert split_code("SH.600519") == (1, "sh", "600519")
    assert split_code("000001") == (0, "sz", "000001")
    assert split_code("430047") == (2, "bj", "430047")


def test_parse_company_profile_fixture() -> None:
    raw = _load("f10_company_profile.json")
    resp = parse_tqlex_response("CWServ.tdxf10_gg_gsgk", {"Params": []}, raw)
    assert resp.ok
    assert len(resp.result_sets) >= 1
    table = resp.first_table
    assert table is not None
    assert table.count >= 1
    row = resp.first_row()
    assert row is not None
    assert row["T035"] == "A股"
    assert row["T042"] == 31.39  # 发行价


def test_parse_announcements_fixture() -> None:
    raw = _load("f10_announcements.json")
    resp = parse_tqlex_response("CWSearch.tzx_rcache", {}, raw)
    assert resp.rows
    row = resp.rows[0]
    assert "title" in row
    assert "url" in row


def test_parse_handles_missing_sets() -> None:
    resp = parse_tqlex_response("X", {}, {"ErrorCode": 1})
    assert not resp.ok
    assert resp.result_sets == ()
    assert resp.rows == ()


def test_f10client_company_profile_calls_entry() -> None:
    raw = _load("f10_company_profile.json")
    fake = _FakeTransport(raw)
    client = F10Client(transport=fake)
    resp = client.company_profile("600519")
    assert fake.calls == [("CWServ.tdxf10_gg_gsgk", {"Params": ["8", "600519", ""]})]
    assert resp.ok and resp.first_row()["T035"] == "A股"


def test_f10client_valuation_body_shape() -> None:
    fake = _FakeTransport({"ErrorCode": 0, "ResultSets": []})
    client = F10Client(transport=fake)
    client.valuation("600519")
    entry, body = fake.calls[0]
    assert entry == "HQServ.hq_nlp_gpsj"
    assert isinstance(body, list)
    assert body[0]["ReqId"] == "200191"
    assert body[0]["Code"] == "600519|1"


def test_f10client_announcements_cache_key() -> None:
    fake = _FakeTransport({"ErrorCode": 0, "ResultSets": []})
    client = F10Client(transport=fake)
    client.announcements("sh600519")
    entry, body = fake.calls[0]
    assert entry == "CWSearch.tzx_rcache"
    assert body["key"] == "gg:1_600519"
    assert body["action"] == "get"


def test_limit_up_down_list_date_normalization() -> None:
    fake = _FakeTransport({"ErrorCode": 0, "ResultSets": []})
    client = F10Client(transport=fake)
    client.limit_up_down_list("2026-09-01", 20260915)
    entry, body = fake.calls[0]
    assert entry == "CWServ.cfg_fx_lbtt"
    assert body == {"Params": ["1", "20260901", "20260915"]}


def test_cache_avoids_duplicate_requests() -> None:
    raw = _load("f10_company_profile.json")
    fake = _FakeTransport(raw)
    client = F10Client(transport=fake, cache=True)
    client.company_profile("600519")
    client.company_profile("600519")
    assert len(fake.calls) == 1  # 第二次命中缓存
    client.clear_cache()
    client.company_profile("600519")
    assert len(fake.calls) == 2


def test_no_cache_by_default() -> None:
    raw = _load("f10_company_profile.json")
    fake = _FakeTransport(raw)
    client = F10Client(transport=fake)
    client.company_profile("600519")
    client.company_profile("600519")
    assert len(fake.calls) == 2


class _PagedTransport:
    """按 page 参数返回不同页的假传输层。"""

    def __init__(self, total: int, page_size: int) -> None:
        self.base_url = "http://fake/TQLEX"
        self.timeout = 1.0
        self.retries = 0
        self.total = total
        self.page_size = page_size
        self.calls = 0

    def post(self, entry: str, body: Any) -> dict[str, Any]:
        self.calls += 1
        page = int(body["Params"][4])
        start = (page - 1) * self.page_size
        count = max(0, min(self.page_size, self.total - start))
        content = [[f"t{start + i}", "20260101"] for i in range(count)]
        return {
            "ErrorCode": 0,
            "ResultSets": [{"ColName": ["T039", "T012"], "Content": content}],
        }


def test_company_news_all_paginates() -> None:
    fake = _PagedTransport(total=45, page_size=20)
    client = F10Client(transport=fake)
    rows = client.company_news_all("600519", page_size=20)
    assert len(rows) == 45
    assert fake.calls == 3  # 20 + 20 + 5


def test_async_f10_client() -> None:
    import asyncio

    from easy_tdx.f10 import AsyncF10Client

    raw = _load("f10_company_profile.json")
    fake = _FakeTransport(raw)
    client = AsyncF10Client(transport=fake)

    async def main() -> dict[str, Any]:
        resp = await client.company_profile("600519")
        return resp.first_row()

    row = asyncio.run(main())
    assert fake.calls == [("CWServ.tdxf10_gg_gsgk", {"Params": ["8", "600519", ""]})]
    assert row["T035"] == "A股"
