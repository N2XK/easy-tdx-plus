"""7615 F10 / TQLEX 数据模型。

TQLEX 是通达信 F10 资料数据的 HTTP 网关（非二进制协议）：
``POST <base>?Entry=<entry>``，body 为 JSON，响应 ``{ResultSets, ErrorCode}``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class F10ResultSet:
    """TQLEX 返回的一张结果表。"""

    key: str | None
    columns: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def count(self) -> int:
        return len(self.rows)

    def first(self) -> dict[str, Any] | None:
        return self.rows[0] if self.rows else None


@dataclass(frozen=True)
class F10Response:
    """一次 TQLEX Entry 调用的解析结果。"""

    entry: str
    request_body: Any
    error_code: int | None
    result_sets: tuple[F10ResultSet, ...]
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def ok(self) -> bool:
        return self.error_code in (None, 0)

    @property
    def tables(self) -> tuple[F10ResultSet, ...]:
        return self.result_sets

    @property
    def first_table(self) -> F10ResultSet | None:
        return self.result_sets[0] if self.result_sets else None

    @property
    def rows(self) -> tuple[dict[str, Any], ...]:
        table = self.first_table
        return table.rows if table is not None else ()

    def first_row(self) -> dict[str, Any] | None:
        table = self.first_table
        return table.first() if table is not None else None
