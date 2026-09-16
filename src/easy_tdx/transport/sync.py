"""同步 TCP 连接（基于 socket）。"""

import socket
import threading
import time
from types import TracebackType
from typing import TYPE_CHECKING, TypeVar

from ..codec.frame import HEADER_SIZE, decompress_body, parse_header
from ..commands.setup import SETUP_COMMANDS
from ..config import (
    get_best_host,
    get_calc_hosts,
    get_known_hosts,
    get_mac_hosts,
    get_port,
    get_timeout,
)
from ..exceptions import TdxConnectionError

if TYPE_CHECKING:
    from ..commands.base import BaseCommand

T = TypeVar("T")

_DEFAULT_HEARTBEAT_INTERVAL = 15.0
_MAX_CONSECUTIVE_HEARTBEATS = 20

# 模块级别名，供外部 `from easy_tdx.transport.sync import KNOWN_HOSTS` 使用。
# 在 import 时从配置读取一次；用户修改 config.json 后需重启生效。
KNOWN_HOSTS = get_known_hosts()
CALC_HOSTS = get_calc_hosts()
MAC_HOSTS = get_mac_hosts()


def ping_host(
    host: str,
    port: int | None = None,
    timeout: float = 5.0,
) -> float | None:
    """测量连接到指定服务器并完成握手所需的时间（秒）。

    返回延迟（秒），连接失败时返回 None。
    """
    if port is None:
        port = get_port()
    t0 = time.monotonic()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
        # 发送第一条握手命令并等待响应作为可用性验证
        sock.sendall(SETUP_COMMANDS[0])
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


def ping_all(
    hosts: list[str] | None = None,
    port: int | None = None,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发测量多台服务器延迟，返回按延迟排序的 (host, latency_seconds) 列表。

    不可达的服务器不包含在结果中。
    """
    if hosts is None:
        hosts = get_known_hosts()
    if port is None:
        port = get_port()
    import concurrent.futures

    results: list[tuple[str, float]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as pool:
        futures = {pool.submit(ping_host, h, port, timeout): h for h in hosts}
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


def ping_mac_all(
    hosts: list[str] | None = None,
    port: int | None = None,
    timeout: float = 5.0,
) -> list[tuple[str, float]]:
    """并发测量多台 MAC 服务器延迟，返回按延迟排序的 (host, latency_seconds) 列表。"""
    if hosts is None:
        hosts = get_mac_hosts()
    return ping_all(hosts=hosts, port=port, timeout=timeout)


def _recv_exact_sock(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise TdxConnectionError("连接被服务器关闭")
        buf.extend(chunk)
    return bytes(buf)


class TdxConnection:
    """同步通达信 TCP 连接。

    使用示例::

        with TdxConnection("180.153.18.170") as conn:
            result = conn.execute(SomeCommand(...))
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.host = host if host is not None else get_best_host()
        self.port = port if port is not None else get_port()
        self.timeout = timeout if timeout is not None else get_timeout()
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._heartbeat_interval: float = 0  # 0 = disabled
        self._stop_event: threading.Event | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._last_active: float = 0.0
        self._consecutive_heartbeats: int = 0

    def connect(self) -> None:
        """建立 TCP 连接并完成握手（发送3条 setup 命令）。"""
        with self._lock:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            try:
                sock.connect((self.host, self.port))
            except OSError as e:
                sock.close()
                raise TdxConnectionError(f"无法连接 {self.host}:{self.port}: {e}") from e
            self._sock = sock
            try:
                self._send_setup()
            except Exception:
                try:
                    sock.close()
                except OSError:
                    pass
                self._sock = None
                raise

    def close(self) -> None:
        """关闭连接（与 execute 互斥，避免并发使用中途 socket 被判空）。"""
        self.stop_heartbeat()
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def execute(self, cmd: "BaseCommand[T]") -> T:
        """执行一条命令：发送请求，接收并解压响应，返回解析结果。"""
        with self._lock:
            self._last_active = time.monotonic()
            self._consecutive_heartbeats = 0
            sock = self._sock
            if sock is None:
                raise TdxConnectionError("未连接，请先调用 connect()")
            # 清除服务端主动推送的残留帧，避免与下一条响应错位
            self._drain_pending()
            request = cmd.build_request()
            try:
                sock.sendall(request)
                header_buf = self._recv_exact(HEADER_SIZE)
                header = parse_header(header_buf)
                raw_body = self._recv_exact(header.zipsize)
            except OSError as e:
                raise TdxConnectionError(f"通信错误: {e}") from e
            body = decompress_body(header, raw_body)
            return cmd.parse_response(body)

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "TdxConnection":
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # heartbeat
    # ------------------------------------------------------------------ #

    def start_heartbeat(self, interval: float = _DEFAULT_HEARTBEAT_INTERVAL) -> None:
        """启动心跳守护线程，定期发送 setup 包保活。"""
        self._heartbeat_interval = interval
        self._last_active = time.monotonic()
        self._stop_event = threading.Event()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="tdx-heartbeat",
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        """停止心跳线程。"""
        stop_event = self._stop_event
        thread = self._heartbeat_thread
        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)
        self._stop_event = None
        self._heartbeat_thread = None
        self._heartbeat_interval = 0

    def _heartbeat_loop(self) -> None:
        """心跳循环：在后台线程中运行。"""
        assert self._stop_event is not None
        interval = self._heartbeat_interval
        while not self._stop_event.wait(timeout=interval):
            if time.monotonic() - self._last_active <= interval:
                continue
            with self._lock:
                if self._sock is None:
                    return
                self._consecutive_heartbeats += 1
                if self._consecutive_heartbeats >= _MAX_CONSECUTIVE_HEARTBEATS:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                    return
                try:
                    self._sock.sendall(SETUP_COMMANDS[0])
                    hdr_buf = _recv_exact_sock(self._sock, HEADER_SIZE)
                    hdr = parse_header(hdr_buf)
                    if hdr.zipsize > 0:
                        _recv_exact_sock(self._sock, hdr.zipsize)
                except OSError:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                    self._sock = None
                    return

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    def _send_setup(self) -> None:
        """按序发送三条握手命令并丢弃响应。"""
        assert self._sock is not None
        for cmd_bytes in SETUP_COMMANDS:
            self._sock.sendall(cmd_bytes)
            # 读取并丢弃握手响应
            try:
                hdr_buf = self._recv_exact(HEADER_SIZE)
                hdr = parse_header(hdr_buf)
                if hdr.zipsize > 0:
                    self._recv_exact(hdr.zipsize)
            except OSError:
                # 部分服务器的握手无响应，忽略错误
                pass

    def _recv_exact(self, n: int) -> bytes:
        """循环 recv 直到读满 n 字节。"""
        assert self._sock is not None
        return _recv_exact_sock(self._sock, n)

    def _drain_pending(self) -> None:
        """丢弃套接字中已到达的残留字节（服务端主动推送帧）。

        部分命令（如 0x0fd1、0x044d 等）之后服务端会附带推送帧，若不清理会与
        下一条响应错位，导致后续请求超时。发送请求前先非阻塞清空缓冲区。
        """
        assert self._sock is not None
        try:
            self._sock.setblocking(False)
            while True:
                try:
                    if not self._sock.recv(65536):
                        break
                except (BlockingIOError, InterruptedError):
                    break
        finally:
            self._sock.settimeout(self.timeout)
