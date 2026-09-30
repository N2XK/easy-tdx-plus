"""通达信安装目录检测与路径解析。"""

import os
import sys
from pathlib import Path

from ..exceptions import TdxOfflineError

_WIN_CANDIDATES = [
    Path(r"C:\new_jyplug"),
    Path(r"C:\new_tdx"),
    Path(r"D:\new_jyplug"),
    Path(r"D:\new_tdx"),
]

_UNIX_CANDIDATES = [
    Path.home() / "new_jyplug",
    Path.home() / "new_tdx",
]


def detect_tdx_home() -> Path | None:
    """按优先级检测通达信安装目录。

    1. TDX_HOME 环境变量
    2. 平台常见路径猜测
    """
    env = os.getenv("TDX_HOME")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    candidates = _WIN_CANDIDATES if sys.platform == "win32" else _UNIX_CANDIDATES
    for p in candidates:
        if p.is_dir():
            return p
    return None


def resolve_vipdoc(path: str | Path | None = None) -> Path:
    """解析 vipdoc 数据目录。

    Args:
        path: 显式指定的 vipdoc 路径。为 None 时自动检测。

    Returns:
        vipdoc 目录的 Path 对象。

    Raises:
        TdxOfflineError: 无法定位 vipdoc 目录。
    """
    if path is not None:
        p = Path(path)
        if p.is_dir():
            return p
        raise TdxOfflineError(f"指定的 vipdoc 路径不存在: {p}")
    home = detect_tdx_home()
    if home is None:
        raise TdxOfflineError(
            "无法定位通达信安装目录，请设置 TDX_HOME 环境变量或显式传入 vipdoc 路径"
        )
    vipdoc = home / "vipdoc"
    if not vipdoc.is_dir():
        raise TdxOfflineError(f"vipdoc 目录不存在: {vipdoc}")
    return vipdoc


def _market_to_exchange(market: int) -> str:
    """Market 枚举值 → vipdoc 子目录名（sh/sz/bj）。"""
    if market == 0:  # Market.SZ
        return "sz"
    if market == 1:  # Market.SH
        return "sh"
    if market == 2:  # Market.BJ
        return "bj"
    raise TdxOfflineError(f"不支持的市场代码: {market}")
