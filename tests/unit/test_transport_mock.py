"""transport 层 mock 测试（同步/异步，无网络）。"""

from __future__ import annotations

import asyncio
import struct
import zlib

import pytest

from easy_tdx.commands.setup import SETUP_COMMANDS
from easy_tdx.exceptions import TdxConnectionError
from easy_tdx.transport import sync as tsync
from easy_tdx.transport.async_ import AsyncTdxConnection


def _frame(body: bytes, compress: bool = False) -> bytes:
    raw = zlib.compress(body) if compress else body
    return struct.pack("<IIIHH", 0, 0, 0, len(raw), len(body)) + raw


class _Cmd:
    def build_request(self) -> bytes:
        return b"\x01\x02\x03"

    def parse_response(self, body: bytes) -> str:
        return body.decode("utf-8")


class FakeSocket:
    def __init__(self, incoming: bytes = b"", fail_connect: bool = False) -> None:
        self._buf = bytearray(incoming)
        self.sent = bytearray()
        self.timeout: float | None = None
        self.closed = False
        self._fail_connect = fail_connect

    def settimeout(self, t: float) -> None:
        self.timeout = t

    def setblocking(self, flag: bool) -> None:
        pass

    def connect(self, addr: tuple[str, int]) -> None:
        if self._fail_connect:
            raise OSError("connection refused")

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def recv(self, n: int) -> bytes:
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def close(self) -> None:
        self.closed = True


# --------------------------------------------------------------------------- #
# 同步
# --------------------------------------------------------------------------- #


def test_connect_sends_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b"") * 3)
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    conn = tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
    conn.connect()
    assert bytes(fake.sent) == b"".join(SETUP_COMMANDS)
    conn.close()
    assert fake.closed


def test_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(fail_connect=True)
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    conn = tsync.TdxConnection(host="127.0.0.1", port=1, timeout=1.0)
    with pytest.raises(TdxConnectionError):
        conn.connect()


def test_execute_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b"") * 3 + _frame(b"hello"))
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    conn = tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
    conn.connect()
    monkeypatch.setattr(conn, "_drain_pending", lambda: None)
    assert conn.execute(_Cmd()) == "hello"  # type: ignore[arg-type]


def test_execute_zlib_body(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b"") * 3 + _frame(b"compressed-payload", compress=True))
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    conn = tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
    conn.connect()
    monkeypatch.setattr(conn, "_drain_pending", lambda: None)
    assert conn.execute(_Cmd()) == "compressed-payload"  # type: ignore[arg-type]


def test_execute_without_connect() -> None:
    conn = tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
    with pytest.raises(TdxConnectionError):
        conn.execute(_Cmd())  # type: ignore[arg-type]


def test_execute_closed_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b"") * 3)  # 握手后服务器关闭
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    conn = tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
    conn.connect()
    monkeypatch.setattr(conn, "_drain_pending", lambda: None)
    with pytest.raises(TdxConnectionError):
        conn.execute(_Cmd())  # type: ignore[arg-type]


def test_context_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b"") * 3)
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    with tsync.TdxConnection(host="127.0.0.1", port=7709, timeout=1.0) as conn:
        assert conn._sock is not None
    assert fake.closed


def test_ping_host_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(incoming=_frame(b""))
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    latency = tsync.ping_host("127.0.0.1", port=7709, timeout=1.0)
    assert latency is not None and latency >= 0


def test_ping_host_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(fail_connect=True)
    monkeypatch.setattr(tsync.socket, "socket", lambda *a, **k: fake)
    assert tsync.ping_host("127.0.0.1", port=1, timeout=1.0) is None


def test_ping_all_sorts_and_drops_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    latencies = {"a": 0.03, "b": None, "c": 0.01}
    monkeypatch.setattr(tsync, "ping_host", lambda host, port, timeout: latencies[host])
    result = tsync.ping_all(hosts=["a", "b", "c"], port=7709, timeout=1.0)
    assert result == [("c", 0.01), ("a", 0.03)]


# --------------------------------------------------------------------------- #
# 异步
# --------------------------------------------------------------------------- #


class FakeReader:
    def __init__(self, incoming: bytes = b"") -> None:
        self._buf = bytearray(incoming)

    async def readexactly(self, n: int) -> bytes:
        if len(self._buf) < n:
            raise asyncio.IncompleteReadError(bytes(self._buf), n)
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk


class FakeWriter:
    def __init__(self) -> None:
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        pass

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def _attach(conn: AsyncTdxConnection, reader: FakeReader, writer: FakeWriter) -> None:
    conn._reader = reader  # type: ignore[assignment]
    conn._writer = writer  # type: ignore[assignment]


def test_async_execute_roundtrip() -> None:
    async def main() -> str:
        conn = AsyncTdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
        _attach(conn, FakeReader(_frame(b"async-hello")), FakeWriter())
        return await conn.execute(_Cmd())  # type: ignore[arg-type]

    assert asyncio.run(main()) == "async-hello"


def test_async_execute_zlib() -> None:
    async def main() -> str:
        conn = AsyncTdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
        _attach(conn, FakeReader(_frame(b"z", compress=True)), FakeWriter())
        return await conn.execute(_Cmd())  # type: ignore[arg-type]

    assert asyncio.run(main()) == "z"


def test_async_execute_not_connected() -> None:
    async def main() -> None:
        conn = AsyncTdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
        with pytest.raises(TdxConnectionError):
            await conn.execute(_Cmd())  # type: ignore[arg-type]

    asyncio.run(main())


def test_async_execute_incomplete_read() -> None:
    async def main() -> None:
        conn = AsyncTdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
        _attach(conn, FakeReader(b"\x00\x00"), FakeWriter())
        with pytest.raises(TdxConnectionError):
            await conn.execute(_Cmd())  # type: ignore[arg-type]

    asyncio.run(main())


def test_async_connect_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = FakeReader(_frame(b"") * 3)
    writer = FakeWriter()

    async def fake_open_connection(host: str, port: int) -> tuple[FakeReader, FakeWriter]:
        return reader, writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    async def main() -> None:
        conn = AsyncTdxConnection(host="127.0.0.1", port=7709, timeout=1.0)
        await conn.connect()
        assert bytes(writer.written) == b"".join(SETUP_COMMANDS)
        await conn.close()

    asyncio.run(main())
