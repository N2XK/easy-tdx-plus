"""集中管理服务器地址、端口、超时等配置。

优先级：环境变量 > ~/.easy_tdx/config.json > 源码内嵌默认值。

配置文件示例::

    {
      "best_host": "180.153.18.170",
      "best_host_updated_at": "2026-05-22T10:30:00",
      "known_hosts": ["111.229.247.189", ...],
      "calc_hosts": ["120.76.152.87"],
      "mac_hosts": ["121.36.248.138", ...],
      "port": 7709,
      "timeout": 15.0
    }

环境变量覆盖::

    EASY_TDX_HOST        -- 单台主机地址
    EASY_TDX_PORT        -- 端口
    EASY_TDX_TIMEOUT     -- 超时秒数
    EASY_TDX_KNOWN_HOSTS -- 逗号分隔的候选主机列表
    EASY_TDX_RETRY_DELAYS-- 断线重试退避序列（逗号分隔秒数）
    EASY_TDX_CONFIG_DIR  -- 配置文件目录（默认 ~/.easy_tdx）
"""

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, cast

_SAVE_LOCK = threading.Lock()

_CONFIG_DIR = Path(os.environ.get("EASY_TDX_CONFIG_DIR", str(Path.home() / ".easy_tdx")))
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# 源码内嵌默认值（config.json 不存在或字段缺失时的兜底）
# ---------------------------------------------------------------------------

# 已验证支持标准协议 K 线（get_security_bars / get_index_bars）的服务器。
# 通达信部分纯报价服务器不响应标准 K 线命令（返回 2 字节残缺响应），
# 故将这些主机置于候选列表最前，保证延迟优选后仍能取到 K 线数据。
_KLINE_CAPABLE_HOSTS: list[str] = [
    "59.36.5.11",
    "117.34.114.14",
    "117.34.114.15",
    "117.34.114.16",
    "117.34.114.17",
    "117.34.114.18",
    "117.34.114.20",
    "117.34.114.27",
]

_FALLBACK_HOSTS: list[str] = [
    *_KLINE_CAPABLE_HOSTS,
    "111.229.247.189",
    "150.158.160.2",
    "180.153.18.170",
    "124.71.187.122",
    "180.153.18.171",
    "180.153.18.172",
    "119.147.212.81",
    "115.238.56.198",
    "115.238.90.165",
    "218.75.126.9",
    "47.107.75.159",
    "59.175.238.38",
    "110.41.147.114",
    "110.41.2.72",
    "101.33.225.16",
    "175.178.112.197",
    "175.178.128.227",
    "43.139.95.83",
    "124.223.163.242",
    "122.51.120.217",
    "123.60.164.122",
    "124.70.199.56",
    "62.234.50.143",
    "81.70.151.186",
    "82.156.214.79",
    "159.75.29.111",
    "43.139.18.171",
    "81.71.32.47",
    "122.51.232.182",
    "118.25.98.114",
    "121.36.225.169",
    "123.60.70.228",
    "123.60.73.44",
    "124.70.133.119",
    "124.71.187.72",
    "119.97.185.59",
    "129.204.230.128",
    "101.42.240.54",
    "124.71.9.153",
    "123.60.84.66",
    "111.230.186.52",
    "101.43.159.194",
    "120.53.8.251",
    "152.136.191.169",
    "116.205.163.254",
    "116.205.171.132",
    "116.205.183.150",
    "49.232.15.141",
    "82.156.174.84",
    "101.42.164.241",
    "101.35.121.35",
    "111.231.113.208",
]

_FALLBACK_CALC_HOSTS: list[str] = [
    "120.76.152.87",
]

_FALLBACK_MAC_HOSTS: list[str] = [
    "121.36.248.138",
    "123.60.47.136",
    "121.37.207.165",
]

_FALLBACK_EX_HOSTS: list[str] = [
    "112.74.214.43",
    "120.25.218.6",
    "43.139.173.246",
    "159.75.90.107",
    "106.52.170.195",
    "139.9.191.175",
    "175.24.47.69",
    "150.158.9.199",
    "150.158.20.127",
    "49.235.119.116",
    "49.234.13.160",
    "116.205.143.214",
    "124.71.223.19",
    "113.45.175.47",
    "123.60.173.210",
    "118.89.69.202",
]

_FALLBACK_MAC_EX_HOSTS: list[str] = [
    "116.205.135.205",
    "121.37.232.167",
]

_FALLBACK_PORT = 7709
_FALLBACK_TIMEOUT = 15.0
_FALLBACK_RETRY_DELAYS: tuple[float, ...] = (0.1, 0.5, 1.0, 2.0)


# ---------------------------------------------------------------------------
# 内部读写
# ---------------------------------------------------------------------------


def _load() -> dict[str, Any]:
    try:
        if _CONFIG_FILE.exists():
            return cast("dict[str, Any]", json.loads(_CONFIG_FILE.read_text("utf-8")))
    except Exception:
        pass
    return {}


def _save(data: dict[str, Any]) -> None:
    # 并发安全：用进程/线程唯一的临时文件名 + 进程内锁，避免多线程同时写导致
    # 一方 replace 后另一方 tmp 丢失（ParallelTdx 回退时会多线程写配置）。
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_FILE.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    with _SAVE_LOCK:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(_CONFIG_FILE)


# ---------------------------------------------------------------------------
# 公开 getter
# ---------------------------------------------------------------------------


def _merge_hosts(primary: list[str], extra: list[str]) -> list[str]:
    """合并主机列表：保留 primary 顺序，追加 extra 中未出现的主机。

    config.json 中的主机列表是首次运行时写入的快照，会掩盖后续版本新增
    的内置主机。这里以内置列表为主、已保存列表为辅做并集，保证新增主机
    （如支持标准协议 K 线的服务器）始终可用。
    """
    merged = list(primary)
    for host in extra:
        if host not in merged:
            merged.append(host)
    return merged


def get_best_host() -> str:
    """返回当前最佳主机地址。优先级：环境变量 > config.json > 默认列表首个。"""
    env = os.environ.get("EASY_TDX_HOST")
    if env:
        return env
    cfg = _load()
    return cast("str", cfg.get("best_host", _FALLBACK_HOSTS[0]))


def get_known_hosts() -> list[str]:
    """返回候选行情主机列表。"""
    env = os.environ.get("EASY_TDX_KNOWN_HOSTS")
    if env:
        return [h.strip() for h in env.split(",") if h.strip()]
    cfg = _load()
    return _merge_hosts(list(_FALLBACK_HOSTS), cfg.get("known_hosts", []))


def get_full_featured_hosts() -> list[str]:
    """返回已验证支持全部标准协议命令的全功能服务器列表。

    通达信部分服务器为旧版/纯报价节点，不响应实时行情、逐笔成交、
    标准协议 K 线等命令（返回残缺或空响应）。这些全功能节点可作为
    自动回退的目标主机。
    """
    env = os.environ.get("EASY_TDX_FULL_HOSTS")
    if env:
        return [h.strip() for h in env.split(",") if h.strip()]
    return list(_KLINE_CAPABLE_HOSTS)


def get_calc_hosts() -> list[str]:
    """返回计算服务器列表。"""
    cfg = _load()
    return _merge_hosts(list(_FALLBACK_CALC_HOSTS), cfg.get("calc_hosts", []))


def get_mac_hosts() -> list[str]:
    """返回 MAC 行情服务器列表。"""
    cfg = _load()
    return _merge_hosts(list(_FALLBACK_MAC_HOSTS), cfg.get("mac_hosts", []))


def get_ex_hosts() -> list[str]:
    """返回扩展行情服务器列表。"""
    cfg = _load()
    return _merge_hosts(list(_FALLBACK_EX_HOSTS), cfg.get("ex_hosts", []))


def get_best_ex_host() -> str:
    """返回当前最佳扩展行情主机。"""
    env = os.environ.get("EASY_TDX_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast("str", cfg.get("best_ex_host", _FALLBACK_EX_HOSTS[0]))


def get_mac_ex_hosts() -> list[str]:
    """返回 MAC 协议扩展行情服务器列表。"""
    cfg = _load()
    return _merge_hosts(list(_FALLBACK_MAC_EX_HOSTS), cfg.get("mac_ex_hosts", []))


def get_best_mac_ex_host() -> str:
    """返回当前最佳 MAC 协议扩展行情主机。"""
    env = os.environ.get("EASY_TDX_MAC_EX_HOST")
    if env:
        return env
    cfg = _load()
    return cast("str", cfg.get("best_mac_ex_host", _FALLBACK_MAC_EX_HOSTS[0]))


def get_port() -> int:
    """返回默认端口。"""
    env = os.environ.get("EASY_TDX_PORT")
    if env:
        return int(env)
    cfg = _load()
    return cast("int", cfg.get("port", _FALLBACK_PORT))


def get_timeout() -> float:
    """返回默认超时秒数。"""
    env = os.environ.get("EASY_TDX_TIMEOUT")
    if env:
        return float(env)
    cfg = _load()
    return cast("float", cfg.get("timeout", _FALLBACK_TIMEOUT))


def get_capability_cache() -> dict[str, Any]:
    """返回持久化的服务器能力缓存 ``{host:port: {"ts":..., "caps": {...}}}``。"""
    value = _load().get("capabilities", {})
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def save_capability(key: str, caps: dict[str, bool]) -> None:
    """把某服务器的能力探测结果持久化到 config.json（供后续启动直接选路）。"""
    cfg = _load()
    table = cfg.setdefault("capabilities", {})
    if not isinstance(table, dict):
        table = {}
        cfg["capabilities"] = table
    table[key] = {"ts": datetime.now().isoformat(), "caps": caps}
    _save(cfg)


def get_retry_delays() -> tuple[float, ...]:
    """返回断线重试的退避序列（秒）。

    优先级：环境变量 ``EASY_TDX_RETRY_DELAYS``（逗号分隔，如 "0.1,0.5,1"）
    > config.json 的 ``retry_delays`` 数组 > 内嵌默认 ``(0.1, 0.5, 1.0, 2.0)``。
    返回空元组表示不重试。
    """
    env = os.environ.get("EASY_TDX_RETRY_DELAYS")
    if env is not None:
        return tuple(float(x) for x in env.split(",") if x.strip())
    cfg = _load()
    value = cfg.get("retry_delays")
    if isinstance(value, list):
        return tuple(float(x) for x in value)
    return _FALLBACK_RETRY_DELAYS


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def save_best_host(host: str) -> None:
    """保存最佳主机到配置文件；首次写入时同时补全默认配置。"""
    cfg = _load()
    cfg["best_host"] = host
    cfg["best_host_updated_at"] = datetime.now().isoformat()
    if "known_hosts" not in cfg:
        cfg["known_hosts"] = list(_FALLBACK_HOSTS)
    if "calc_hosts" not in cfg:
        cfg["calc_hosts"] = list(_FALLBACK_CALC_HOSTS)
    if "mac_hosts" not in cfg:
        cfg["mac_hosts"] = list(_FALLBACK_MAC_HOSTS)
    if "port" not in cfg:
        cfg["port"] = _FALLBACK_PORT
    if "ex_hosts" not in cfg:
        cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)


def save_best_ex_host(host: str) -> None:
    """保存最佳扩展行情主机到配置文件。"""
    cfg = _load()
    cfg["best_ex_host"] = host
    cfg["best_ex_host_updated_at"] = datetime.now().isoformat()
    if "ex_hosts" not in cfg:
        cfg["ex_hosts"] = list(_FALLBACK_EX_HOSTS)
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)


def save_best_mac_ex_host(host: str) -> None:
    """保存最佳 MAC 协议扩展行情主机到配置文件。"""
    cfg = _load()
    cfg["best_mac_ex_host"] = host
    cfg["best_mac_ex_host_updated_at"] = datetime.now().isoformat()
    if "mac_ex_hosts" not in cfg:
        cfg["mac_ex_hosts"] = list(_FALLBACK_MAC_EX_HOSTS)
    _save(cfg)
