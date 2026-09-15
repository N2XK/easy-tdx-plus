"""TQLEX 响应解析（纯函数，便于离线测试）。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..exceptions import TdxDecodeError
from .models import F10Response, F10ResultSet


def _columns(raw: Mapping[str, Any]) -> list[str]:
    for key in ("ColName", "ColDes"):
        value = raw.get(key)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            continue
        names: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                names.append(str(item.get("Name", "")))
            else:
                names.append(str(item))
        return names
    return []


def _row_values(row: Any) -> list[Any]:
    if isinstance(row, Sequence) and not isinstance(row, (str, bytes, bytearray)):
        return list(row)
    return [row]


def _row_dict(columns: list[str], values: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    counts: dict[str, int] = {}
    for index, value in enumerate(values):
        name = columns[index] if index < len(columns) and columns[index] else f"col_{index}"
        seen = counts.get(name, 0)
        counts[name] = seen + 1
        key = name if seen == 0 else f"{name}__{seen + 1}"
        result[key] = value
    return result


def _parse_result_set(raw: Any, index: int) -> F10ResultSet:
    if not isinstance(raw, Mapping):
        raise TdxDecodeError("TQLEX ResultSet 必须是对象")
    columns = _columns(raw)
    content = raw.get("Content") or ()
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes, bytearray)):
        raise TdxDecodeError("TQLEX Content 必须是数组")
    rows = tuple(_row_dict(columns, _row_values(row)) for row in content)
    key = raw.get("ResultSetKey")
    return F10ResultSet(
        key=str(key) if key is not None else None,
        columns=tuple(columns),
        rows=rows,
        raw=dict(raw),
    )


def parse_tqlex_response(entry: str, request_body: Any, raw: Mapping[str, Any]) -> F10Response:
    """将 TQLEX 原始 JSON 解析为 ``F10Response``。"""
    result_sets_raw = raw.get("ResultSets") or ()
    if not isinstance(result_sets_raw, Sequence) or isinstance(
        result_sets_raw, (str, bytes, bytearray)
    ):
        raise TdxDecodeError("TQLEX ResultSets 必须是数组")
    result_sets = tuple(_parse_result_set(item, i) for i, item in enumerate(result_sets_raw))
    error_code_raw = raw.get("ErrorCode")
    error_code = int(error_code_raw) if error_code_raw is not None else None
    return F10Response(
        entry=entry,
        request_body=request_body,
        error_code=error_code,
        result_sets=result_sets,
        raw=dict(raw),
    )
