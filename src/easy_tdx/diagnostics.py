"""有界请求的逐次尝试诊断。

供 :meth:`TdxClient.request` / :meth:`AsyncTdxClient.request` 记录每次实际网络
访问的节点、耗时、异常与最终来源，使调用方无需接触私有 ``_execute`` 也能掌握
网络预算与选路过程。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AttemptDiagnostic:
    """单次节点尝试的结果。"""

    host: str
    ok: bool
    elapsed: float
    error: str | None = None
    empty: bool = False


@dataclass(frozen=True)
class RequestDiagnostics:
    """一次有界请求的完整诊断。"""

    command: str
    attempts: tuple[AttemptDiagnostic, ...]
    source: str | None
    elapsed: float
    exhausted: bool

    @property
    def attempt_count(self) -> int:
        """实际尝试的节点次数。"""
        return len(self.attempts)

    @property
    def hosts(self) -> tuple[str, ...]:
        """按尝试顺序访问过的节点。"""
        return tuple(a.host for a in self.attempts)
