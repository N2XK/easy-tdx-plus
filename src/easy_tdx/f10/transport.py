"""TQLEX（7615 F10）HTTP 传输层。

纯标准库实现（urllib），无第三方依赖。
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..exceptions import TdxConnectionError

_DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "easy-tdx/1.0",
}


def _decode_json(raw_bytes: bytes, lenient: bool) -> Any:
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    if not lenient:
        return json.loads(text)
    # ICFQS 等端点会在 JSON 前后附带非 JSON 前缀；从首个 { 起解析一个完整对象。
    start = text.find("{")
    if start < 0:
        raise ValueError("响应中未找到 JSON 对象")
    parsed, _ = json.JSONDecoder().raw_decode(text[start:])
    return parsed


class TqlexTransport:
    """TQLEX HTTP 客户端。

    Args:
        base_url: 网关基址，如 ``http://static.tdx.com.cn:7615/TQLEX``。
        timeout: 单次请求超时秒数。
        retries: 网络错误时的重试次数。
        headers: 覆盖默认请求头。
        lenient_json: 容忍响应中的非 JSON 前缀（ICFQS 端点需要）。
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 8.0,
        retries: int = 2,
        headers: dict[str, str] | None = None,
        lenient_json: bool = False,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.retries = max(0, retries)
        self.lenient_json = lenient_json
        self.headers = dict(_DEFAULT_HEADERS)
        if headers:
            self.headers.update(headers)

    def post(self, entry: str, body: Any) -> dict[str, Any]:
        """向指定 Entry 发送 POST，返回原始 JSON（dict）。"""
        url = f"{self.base_url}?{urlencode({'Entry': entry})}"
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            request = Request(url, data=data, headers=self.headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    raw_bytes = response.read()
                parsed = _decode_json(raw_bytes, self.lenient_json)
                if not isinstance(parsed, dict):
                    raise TdxConnectionError(f"TQLEX 返回非对象 JSON: {entry}")
                return parsed
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(0.3 * (attempt + 1))
                    continue
        raise TdxConnectionError(f"TQLEX 请求失败 ({entry}): {last_exc}")
