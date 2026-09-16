"""ICFQS 7615 客户端测试（离线，假传输层）。"""

from __future__ import annotations

from typing import Any

from easy_tdx.f10.icfqs import DEFAULT_ICFQS_ADDRESS, IcfqsClient
from easy_tdx.f10.transport import _decode_json

_RESP = {"ErrorCode": 0, "ResultSets": [{"ColName": ["rq"], "Content": [["20260915"]]}]}


class _FakeTransport:
    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.base_url = "http://fake/TQLEX"
        self.timeout = 1.0
        self.retries = 0
        self.lenient_json = True
        self.response = response or _RESP
        self.calls: list[tuple[str, Any]] = []

    def post(self, entry: str, body: Any) -> dict[str, Any]:
        self.calls.append((entry, body))
        return self.response


def test_default_base_url() -> None:
    c = IcfqsClient(transport=_FakeTransport())
    assert c.base_url == f"http://{DEFAULT_ICFQS_ADDRESS}/TQLEX"


def test_lhb_detail_params() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).lhb_detail("600519", "20260801", "20260915")
    entry, body = fake.calls[0]
    assert entry == "CWServ.cfg_fx_yzlhb"
    assert body == {
        "Params": ["yybxq", "20260801", "20260915", "600519", "", 0, 2000],
        "oauth_zzfw": "1",
    }


def test_lhb_yyb_params() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).lhb_yyb_detail("东方财富证券股份有限公司", "20260801", "20260915")
    entry, body = fake.calls[0]
    assert entry == "CWServ.cfg_fx_yzlhb"
    assert body["Params"] == [
        "tjyyb",
        "20260801",
        "20260915",
        "",
        "东方财富证券股份有限公司",
        0,
        2000,
    ]


def test_daily_review_params() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).daily_review("rq", date="0", limit=30)
    assert fake.calls[0][1] == {"Params": ["0", "rq", "", 0, 30], "oauth_zzfw": "1"}


def test_topics_hot_and_search() -> None:
    fake = _FakeTransport()
    c = IcfqsClient(transport=fake)
    c.topics_hot()
    c.topic_search("芯片")
    assert fake.calls[0][1]["Params"] == ["00302", "", 1]
    assert fake.calls[1][1]["Params"] == ["00102", "芯片", "0"]


def test_topic_stocks_params() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).topic_stocks("881001", "1", page=2, size=50)
    assert fake.calls[0][1]["Params"] == ["00901", "881001", "1", 1, 50, 0, 2]


def test_topic_quotes_body_is_list() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).topic_quotes([("1", "600519")])
    entry, body = fake.calls[0]
    assert entry == "HQServ.hq_nlp"
    assert isinstance(body, list)
    assert body[0]["ReqId"] == "200800"
    assert body[0]["Code"] == ["600519"]


def test_topic_rotation_body() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).topic_rotation()
    entry, body = fake.calls[0]
    assert entry == "HQServ.hq_nlp_copilot"
    assert body[0]["ReqId"] == "200773"


def test_quotes_batch_body() -> None:
    fake = _FakeTransport()
    IcfqsClient(transport=fake).quotes_batch([("1", "600519")], want_columns=["NOW"])
    entry, body = fake.calls[0]
    assert entry == "HQServ.PBCombHQ"
    assert body == {"Setcode": ["1"], "Head": {"Target": 0}, "WantCol": ["NOW"], "Code": ["600519"]}


def test_response_parsed() -> None:
    r = IcfqsClient(transport=_FakeTransport()).daily_review("rq")
    assert r.rows[0]["rq"] == "20260915"


def test_lenient_json_prefers_first_object() -> None:
    parsed = _decode_json(b'garbage{"a":1}trailing', lenient=True)
    assert parsed == {"a": 1}
