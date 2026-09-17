def test_heartbeat_loop_exits_quietly_on_disconnect() -> None:
    """服务器关闭连接时心跳线程不得抛出未捕获异常（TdxConnectionError）。"""
    import threading

    from easy_tdx.exceptions import TdxConnectionError
    from easy_tdx.transport.sync import TdxConnection

    class _DeadSock:
        def sendall(self, data: bytes) -> None:  # noqa: ARG002
            raise TdxConnectionError("连接被服务器关闭")

        def close(self) -> None:
            pass

    errors: list[BaseException] = []
    prev_hook = threading.excepthook

    def hook(args) -> None:  # noqa: ANN001
        if args.exc_value is not None:
            errors.append(args.exc_value)

    threading.excepthook = hook
    try:
        conn = TdxConnection("127.0.0.1", 7709, timeout=1.0)
        conn._sock = _DeadSock()  # type: ignore[assignment]
        conn._last_active = 0.0
        conn._stop_event = threading.Event()
        conn._heartbeat_interval = 0.01
        t = threading.Thread(target=conn._heartbeat_loop, daemon=True)
        t.start()
        t.join(2.0)
    finally:
        threading.excepthook = prev_hook

    assert not t.is_alive()
    assert conn._sock is None
    assert errors == []
