"""MAC 协议服务器真实接口能力探测。

连接测速只能说明 TCP 可达，**不能**说明所需命令/字段可用。这里用少量代表性
MAC 命令探测每台服务器的分项能力，并把结果区分为三态：

- ``"ok"``    : 命令成功且返回非空；
- ``"empty"`` : 命令成功但返回空（合法无数据，或该字段/命令不被该节点支持，
                需调用方结合业务判断）；
- ``"error"`` : 连接/握手/解析失败（节点异常）。

用于 MAC 选优时，可将 ``require`` 指定为需要的能力（如 ``["quotes"]``），
避免只按延迟选中一个连得上但取不到所需字段的节点。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from ..config import get_port, get_timeout
from ..models.enums import Market
from .commands import SymbolBarCmd, SymbolQuotesCmd
from .enums import Period

if TYPE_CHECKING:
    from ..transport.sync import TdxConnection

# 探针标的：上海贵州茅台（成交活跃，正常交易日必有数据）。
_PROBE_MARKET = Market.SH
_PROBE_CODE = "600519"

# feature -> 构造并执行一条代表性命令
_PROBES: dict[str, Callable[[Any], Any]] = {
    "quotes": lambda c: c.execute(SymbolQuotesCmd([(int(_PROBE_MARKET), _PROBE_CODE)])),
    "kline": lambda c: c.execute(
        SymbolBarCmd(
            market=int(_PROBE_MARKET),
            code=_PROBE_CODE,
            period=Period.DAILY,
            start=0,
            count=5,
        )
    ),
}

MAC_FEATURES: tuple[str, ...] = tuple(_PROBES)


def probe_mac_capabilities(
    host: str,
    port: int | None = None,
    timeout: float | None = None,
    *,
    features: Iterable[str] | None = None,
    connection_factory: Callable[[], TdxConnection] | None = None,
) -> dict[str, str]:
    """探测某 MAC 服务器的分项能力，返回 ``{feature: "ok"|"empty"|"error"}``。

    ``connection_factory`` 供测试注入假连接；连接失败时全部记为 ``"error"``
    （与"命令成功但空返回"的 ``"empty"`` 区分开）。
    """
    from ..transport.sync import TdxConnection as _Conn

    if port is None:
        port = get_port()
    if timeout is None:
        timeout = get_timeout()
    selected = tuple(features) if features is not None else MAC_FEATURES

    factory = connection_factory or (lambda: _Conn(host, port, timeout))
    conn: Any = None
    try:
        conn = factory()
        conn.connect()
    except Exception:
        return {name: "error" for name in selected}

    out: dict[str, str] = {}
    try:
        for name in selected:
            probe = _PROBES.get(name)
            if probe is None:
                continue
            try:
                result = probe(conn)
                out[name] = "ok" if result else "empty"
            except Exception:
                out[name] = "error"
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return out


def select_mac_host(
    ranked: list[tuple[str, float]],
    require: Iterable[str] | None,
    *,
    limit: int = 5,
    prober: Callable[[str], dict[str, str]] | None = None,
) -> str | None:
    """从按延迟排序的 MAC 主机中，选第一台 ``require`` 全部为 ``"ok"`` 的。

    未指定 ``require`` 时返回 None（由调用方走默认逻辑）。
    """
    if not require:
        return None
    wanted = set(require)
    for host, _latency in ranked[:limit]:
        caps = prober(host) if prober is not None else probe_mac_capabilities(host)
        if all(caps.get(f) == "ok" for f in wanted):
            return host
    return None
