"""扩展市场表格 0x2422 测试（离线）。"""

from __future__ import annotations

import asyncio
import struct

from easy_tdx.ex.commands.get_table import GetExTableCmd


def test_ex_table_request_layout() -> None:
    req = GetExTableCmd(0).build_request()
    assert req[0] == 0x01  # head flag (EX)
    assert req[10:12] == b"\x22\x24"  # msg id 0x2422
    payload = req[12:]
    assert len(payload) == 126


def test_ex_table_parse() -> None:
    body = bytearray(169)
    struct.pack_into("<I", body, 35, 0)
    struct.pack_into("<I", body, 161, 2023)
    body += "42#IMCI|上期有色,42#T001|通达信商品".encode("gbk")
    chunk = GetExTableCmd(0).parse_response(bytes(body))
    assert chunk.start == 0
    assert chunk.count == 2023
    assert "上期有色" in chunk.content


def test_async_icfqs_client() -> None:
    from typing import Any

    from easy_tdx.f10.async_icfqs import AsyncIcfqsClient

    class _Fake:
        base_url = "http://fake/TQLEX"
        timeout = 1.0
        retries = 0
        lenient_json = True

        def post(self, entry: str, body: Any) -> dict[str, Any]:
            return {"ErrorCode": 0, "ResultSets": [{"ColName": ["x"], "Content": [[1]]}]}

    async def main() -> int:
        c = AsyncIcfqsClient(transport=_Fake())
        resp = await c.topics_hot()
        return len(resp.rows)

    assert asyncio.run(main()) == 1
