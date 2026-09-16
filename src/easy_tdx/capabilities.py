"""服务器能力探测与按能力选路。

通达信存在旧版/纯报价服务器，能完成握手但不响应某些新命令（K线/逐笔/财务等）。
本模块用少量代表性命令探测每台服务器的**分项能力**，缓存（进程内 + 可持久化到
config.json），用于 `TdxClient.from_best_host(require=[...])` 直接选到满足要求的
服务器，避免"先失败再回退"。
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from .commands.finance_info import GetFinanceInfoCmd
from .commands.security_bars import GetSecurityBarsCmd
from .commands.security_list import GetSecurityListCmd
from .commands.security_quotes import GetSecurityQuotesCmd
from .commands.transaction import GetTransactionDataCmd
from .commands.xdxr_info import GetXdxrInfoCmd
from .config import get_capability_cache, get_port, get_timeout, save_capability
from .models.enums import KlineCategory, Market

if TYPE_CHECKING:
    from .transport.sync import TdxConnection

# 代表性探针（feature -> 构造并执行一条命令）
_PROBES: dict[str, Callable[[Any], Any]] = {
    "quotes": lambda c: c.execute(GetSecurityQuotesCmd([(Market.SH, "600519")])),
    "kline": lambda c: c.execute(GetSecurityBarsCmd(Market.SH, "600519", KlineCategory.DAY, 0, 5)),
    "transaction": lambda c: c.execute(GetTransactionDataCmd(Market.SH, "600519", 0, 10)),
    "finance": lambda c: c.execute(GetFinanceInfoCmd(Market.SH, "600519")),
    "xdxr": lambda c: c.execute(GetXdxrInfoCmd(Market.SH, "600519")),
    "security_list": lambda c: c.execute(GetSecurityListCmd(Market.SH, 0)),
}

FEATURES: tuple[str, ...] = tuple(_PROBES)

_CACHE: dict[str, tuple[float, dict[str, bool]]] = {}
_TTL = 3600.0


def _probe(conn: Any, features: Iterable[str]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for name in features:
        probe = _PROBES.get(name)
        if probe is None:
            continue
        try:
            out[name] = bool(probe(conn))
        except Exception:
            out[name] = False
    return out


def probe_capabilities(
    host: str,
    port: int | None = None,
    timeout: float | None = None,
    *,
    features: Iterable[str] | None = None,
    refresh: bool = False,
    connection_factory: Callable[[], TdxConnection] | None = None,
) -> dict[str, bool]:
    """探测某服务器支持的能力（``{feature: bool}``）。

    结果按主机缓存 1 小时（进程内）；未命中时回看 config.json 的持久化缓存。
    ``port`` / ``timeout`` 缺省时取 config 默认值；``connection_factory`` 供测试注入假连接。
    """
    from .transport.sync import TdxConnection as _Conn

    if port is None:
        port = get_port()
    if timeout is None:
        timeout = get_timeout()
    selected = tuple(features) if features is not None else FEATURES
    key = f"{host}:{port}"

    if not refresh:
        cached = _CACHE.get(key)
        if cached is not None and (time.monotonic() - cached[0]) < _TTL:
            return cached[1]
        saved = get_capability_cache().get(key)
        if isinstance(saved, dict) and isinstance(saved.get("caps"), dict):
            caps = {k: bool(v) for k, v in saved["caps"].items()}
            _CACHE[key] = (time.monotonic(), caps)
            return caps

    factory = connection_factory or (lambda: _Conn(host, port, timeout))
    conn: Any = None
    try:
        conn = factory()
        conn.connect()
        caps = _probe(conn, selected)
    except Exception:
        caps = {name: False for name in selected}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    _CACHE[key] = (time.monotonic(), caps)
    save_capability(key, caps)
    return caps


def select_host(
    ranked: list[tuple[str, float]],
    require: Iterable[str] | None,
    port: int,
    timeout: float,
    *,
    limit: int = 6,
    prober: Callable[[str, int, float], dict[str, bool]] | None = None,
) -> str | None:
    """从按延迟排序的主机中选出满足 ``require`` 全部能力的最低延迟主机。

    未指定 ``require`` 或都不可探测时返回 None（由调用方走默认逻辑）。
    """
    if not require:
        return None
    probe = prober or (lambda h, p, t: probe_capabilities(h, p, t))
    wanted = set(require)
    for host, _latency in ranked[:limit]:
        caps = probe(host, port, timeout)
        if all(caps.get(f) for f in wanted):
            return host
    return None
