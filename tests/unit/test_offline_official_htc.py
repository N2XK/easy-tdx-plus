"""官方下载（downit 清单）与 .htc 分笔容器测试（离线）。"""

from __future__ import annotations

import struct
import zlib

import pytest

from easy_tdx.exceptions import TdxOfflineError
from easy_tdx.offline import iter_htc, parse_downit_cfg, read_htc
from easy_tdx.offline.official import OfficialChannel

_CFG = """
[DOWN]
DOWNNUM=3
TYPE01=1
PATH01=products/data/data/2ktic/
FILE01=YYYYMMDD.zip
TYPE06=6
PATH06=products/data/data/dbf/
FILE06=gbbq.zip
TYPE09=9
PATH09=products/data/data/g3tic/
FILE09=YYYYMMDD.zip
"""


def test_parse_downit_cfg() -> None:
    chans = parse_downit_cfg(_CFG)
    assert [(c.type, c.path, c.file) for c in chans] == [
        (1, "products/data/data/2ktic/", "YYYYMMDD.zip"),
        (6, "products/data/data/dbf/", "gbbq.zip"),
        (9, "products/data/data/g3tic/", "YYYYMMDD.zip"),
    ]


def test_channel_url() -> None:
    ch = OfficialChannel("09", 9, "products/data/data/g3tic/", "YYYYMMDD.zip")
    assert ch.url(date=20240102) == ("http://www.tdx.com.cn/products/data/data/g3tic/20240102.zip")
    with pytest.raises(ValueError):
        ch.url()  # 需要日期
    ch2 = OfficialChannel("06", 6, "products/data/data/dbf/", "gbbq.zip")
    assert ch2.url() == "http://www.tdx.com.cn/products/data/data/dbf/gbbq.zip"


def _htc(entries: list[tuple[int, str, int, bytes]]) -> bytes:
    body = struct.pack("<IIII", 2, 20240102, 20240102, len(entries))
    for market, code, date, payload in entries:
        comp = zlib.compress(payload)
        body += struct.pack(
            "<B7sIIIffH",
            market,
            code.encode(),
            date,
            len(payload),
            len(comp),
            2.0,
            6.0,
            0,
        )
        body += comp
    return body


def test_iter_htc(tmp_path) -> None:
    payload = b"TIC" * 100
    p = tmp_path / "20240102.htc"
    p.write_bytes(_htc([(0, "000001", 20240102, payload), (1, "600519", 20240102, b"AB" * 10)]))
    entries = list(iter_htc(p))
    assert [(e.market, e.code, e.date) for e in entries] == [
        (0, "000001", 20240102),
        (1, "600519", 20240102),
    ]
    assert entries[0].data == payload
    assert entries[0].usize == len(payload)


def test_read_htc_filter(tmp_path) -> None:
    p = tmp_path / "x.htc"
    p.write_bytes(_htc([(0, "000001", 20240102, b"a"), (1, "600519", 20240102, b"b")]))
    got = read_htc(p, codes=["600519"])
    assert set(got) == {"600519"}
    assert got["600519"].data == b"b"


class _FakeResp:
    def __init__(self, body: bytes, headers: dict, status: int = 200) -> None:
        self._body = body
        self.headers = headers
        self.status = status
        self._pos = 0

    def read(self, n: int) -> bytes:
        chunk = self._body[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_download_rejects_truncated(tmp_path, monkeypatch) -> None:
    from easy_tdx.offline import official

    body = b"x" * 10
    monkeypatch.setattr(
        official, "_http_get", lambda *a, **k: _FakeResp(body, {"Content-Length": "99"})
    )
    dest = tmp_path / "gbbq.zip"
    # 声明 99 字节但只给 10 字节 -> 断言不完整，且 .part 保留供续传
    with pytest.raises(TdxOfflineError):
        official.download_channel(official.OfficialChannel("01", 6, "x/", "gbbq.zip"), tmp_path)
    assert not dest.exists()
    assert (tmp_path / "gbbq.zip.part").exists()


def test_download_accepts_complete(tmp_path, monkeypatch) -> None:
    from easy_tdx.offline import official

    body = b"hello"
    monkeypatch.setattr(
        official, "_http_get", lambda *a, **k: _FakeResp(body, {"Content-Length": str(len(body))})
    )
    official.download_channel(official.OfficialChannel("01", 6, "x/", "gbbq.zip"), tmp_path)
    assert (tmp_path / "gbbq.zip").read_bytes() == body


def test_download_resumes_partial(tmp_path, monkeypatch) -> None:
    from easy_tdx.offline import official

    (tmp_path / "gbbq.zip.part").write_bytes(b"abc")
    body = b"defg"
    resp = _FakeResp(body, {"Content-Range": "bytes 3-6/7"}, status=206)
    monkeypatch.setattr(official, "_http_get", lambda *a, **k: resp)
    official.download_channel(official.OfficialChannel("01", 6, "x/", "gbbq.zip"), tmp_path)
    assert (tmp_path / "gbbq.zip").read_bytes() == b"abcdefg"
