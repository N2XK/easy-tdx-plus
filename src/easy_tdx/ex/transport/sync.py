"""扩展行情同步 TCP 连接（端口 7727）。"""

import socket
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar

from ...codec.frame import HEADER_SIZE, decompress_body, parse_header
from ...config import get_best_ex_host, get_ex_hosts
from ...exceptions import TdxConnectionError
from ..commands.get_instrument_count import GetExInstrumentCountCmd

if TYPE_CHECKING:
    from ...commands.base import BaseCommand

T = TypeVar("T")

_DEFAULT_EX_PORT = 7727
_DEFAULT_TIMEOUT = 15.0


def ping_ex_host(
    host: str,
    port: int = _DEFAULT_EX_PORT,
    timeout: float = 5.0,
) -> float | None:
    """测量扩展行情服务器延迟（秒）。通过发送 get_instrument_count 验证可用性。"""
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        cmd = GetExInstrumentCountCmd()
        sock.sendall(cmd.build_request())
        hdr_buf = _recv_exact_sock(sock, HEADER_SIZE)
        hdr = parse_header(hdr_buf)
        if hdr.zipsize > 0:
            _recv_exact_sock(sock, hdr.zipsize)
        return time.monotonic() - t0
    except (OSError, TdxConnectionError):
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass


def ping_ex_all(
    hosts: list[str] | None = None,
    port: int = _DEFAULT_EX_PORT,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发测量多台扩展行情服务器延迟，按延迟排序返回。"""
    import concurrent.futures

    if hosts is None:
        hosts = get_ex_hosts()
    results: list[tuple[str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {pool.submit(ping_ex_host, h, port, timeout): h for h in hosts}
        for fut in concurrent.futures.as_completed(futures):
            host = futures[fut]
            try:
                latency = fut.result()
            except Exception:
                latency = None
            if latency is not None:
                results.append((host, latency))
    results.sort(key=lambda t: t[1])
    return results


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise TdxConnectionError("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


class ExTdxConnection:
    """扩展行情同步 TCP 连接（端口 7727，单包握手）。

    Parameters
    ----------
    mac_ex_mode : bool
        为 True 时自动将 MAC 命令的 head_flag 从 0x1C 转为 0x01，
        以兼容 MAC EX 服务器（需要 head_flag=0x01）。
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = _DEFAULT_EX_PORT,
        timeout: float = _DEFAULT_TIMEOUT,
        *,
        mac_ex_mode: bool = False,
    ) -> None:
        self.host = host if host is not None else get_best_ex_host()
        self.port = port
        self.timeout = timeout
        self.mac_ex_mode = mac_ex_mode
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """建立 TCP 连接。扩展行情服务器不需要握手命令。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
        except OSError as e:
            sock.close()
            raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
        self._sock = sock

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            if self._sock is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            request = cmd.build_request()
            if self.mac_ex_mode and len(request) > 0 and request[0] == 0x1C:
                request = b"\x01" + request[1:]
            try:
                self._sock.sendall(request)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise TdxConnectionError(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return cmd.parse_response(body)

    def __enter__(self) -> "ExTdxConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def _recv_exact(self, n: int) -> bytes:
        assert self._sock is not None
        return _recv_exact_sock(self._sock, n)
