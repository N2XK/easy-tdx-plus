"""通达信官方分笔容器（`.htc`，来自 g3tic/g4tic）读取。

文件结构（逆向自 g3tic 样本）：
  全局头 16 字节：u32(市场/版本)、u32(日期)、u32(日期)、u32(标的数)
  其后为紧凑排列的标的块，每块：
    market(u8) + code(7s ASCII) + date(u32) + usize(u32) + csize(u32)
    + f32 + f32 + u16  （共 30 字节头）
    + zlib(csize 字节) → 解压得 usize 字节的分笔数据

> 说明：本模块解析**容器与外层帧**；解压后的分笔记录为 TDX 变长差分编码，
> 记录级解码尚未实现，``HtcEntry.data`` 给出解压后的原始字节供进一步解析。
"""

from __future__ import annotations

import struct
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from ..exceptions import TdxOfflineError

_HEADER_SIZE = 16
_ENTRY_HEADER_SIZE = 30
_MAX_CSIZE = 4_000_000

__all__ = ["HtcEntry", "iter_htc", "read_htc", "HtcHeader"]


@dataclass
class HtcHeader:
    field0: int
    date: int
    date2: int
    count: int


@dataclass
class HtcEntry:
    market: int
    code: str
    date: int
    usize: int
    compressed: bytes = field(repr=False, default=b"")
    data: bytes = field(repr=False, default=b"")


def _parse_header(buf: bytes) -> HtcHeader:
    field0, date, date2, count = struct.unpack_from("<IIII", buf, 0)
    return HtcHeader(field0, date, date2, count)


def iter_htc(filepath: str | Path) -> Iterator[HtcEntry]:
    """逐个产出 .htc 中的标的条目（含解压后的数据）。"""
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxOfflineError(f"分笔文件不存在: {filepath}")
    data = filepath.read_bytes()
    if len(data) < _HEADER_SIZE:
        raise TdxOfflineError("htc 文件过短")
    pos = _HEADER_SIZE
    total = len(data)
    while pos + _ENTRY_HEADER_SIZE <= total:
        market = data[pos]
        raw_code = data[pos + 1 : pos + 8]
        date, usize, csize = struct.unpack_from("<III", data, pos + 8)
        if not (1 <= csize <= _MAX_CSIZE) or pos + _ENTRY_HEADER_SIZE + csize > total:
            break
        code = raw_code.rstrip(b"\x00").decode("ascii", errors="replace")
        comp = data[pos + _ENTRY_HEADER_SIZE : pos + _ENTRY_HEADER_SIZE + csize]
        try:
            payload = zlib.decompress(comp)
        except zlib.error as e:
            raise TdxOfflineError(f"htc 标的 {code} 解压失败: {e}") from e
        yield HtcEntry(
            market=market, code=code, date=date, usize=usize, compressed=comp, data=payload
        )
        pos += _ENTRY_HEADER_SIZE + csize


def read_htc(filepath: str | Path, codes: list[str] | None = None) -> dict[str, HtcEntry]:
    """读取 .htc，返回 {code: HtcEntry}；``codes`` 非空时仅取这些代码。"""
    want = set(codes) if codes else None
    out: dict[str, HtcEntry] = {}
    for entry in iter_htc(filepath):
        if want is None or entry.code in want:
            out[entry.code] = entry
        if want is not None and len(out) == len(want):
            break
    return out
