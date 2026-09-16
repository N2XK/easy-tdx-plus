"""通达信官方历史数据下载（tdx.com.cn 静态站点）。

官方通过 `downit.zip` 提供数据清单（`downit5.cfg`），列出多个下载通道：
分笔/明细（2ktic、g3tic、g4tic）、日线（g3day、newday、g4day）、
基础数据（dbf/info.zip、dbf/base.zip、dbf/gbbq.zip）、完整 vipdoc.zip 等。

> 注意：这些站点文件按日期归档、体积较大（如 g3tic 单日 ~80MB）；下载支持断点续传。
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..exceptions import TdxOfflineError

DEFAULT_OFFICIAL_BASE = "http://www.tdx.com.cn"
MANIFEST_FILE = "downit.zip"
MANIFEST_CFG = "downit5.cfg"
_DATE_TOKEN = "YYYYMMDD"

__all__ = [
    "OfficialChannel",
    "parse_downit_cfg",
    "fetch_manifest",
    "download_channel",
    "download_by_type",
    "download_named",
    "DEFAULT_OFFICIAL_BASE",
]


@dataclass
class OfficialChannel:
    """一个官方下载通道。"""

    index: str  # 配置项编号 "01".."12"
    type: int  # 类型编号
    path: str  # 相对路径（可能以 / 结尾）
    file: str  # 文件名模板（可能含 YYYYMMDD）

    def url(self, base: str = DEFAULT_OFFICIAL_BASE, date: int | None = None) -> str:
        fname = self.file
        if _DATE_TOKEN in fname:
            if date is None:
                raise ValueError(f"通道 {self.path}{self.file} 需要 date(YYYYMMDD)")
            fname = fname.replace(_DATE_TOKEN, str(date))
        return f"{base.rstrip('/')}/{self.path}{fname}"


def parse_downit_cfg(text: str) -> list[OfficialChannel]:
    """解析 downit5.cfg 文本 → 通道列表（按编号排序）。"""
    items: dict[str, dict[str, str]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        for field in ("TYPE", "PATH", "FILE"):
            if key.startswith(field) and key[len(field) :].isdigit():
                items.setdefault(key[len(field) :], {})[field] = value.strip()
    out: list[OfficialChannel] = []
    for idx in sorted(items):
        d = items[idx]
        if "TYPE" not in d:
            continue
        out.append(
            OfficialChannel(
                index=idx,
                type=int(d["TYPE"] or 0),
                path=d.get("PATH", ""),
                file=d.get("FILE", ""),
            )
        )
    return out


def _http_get(url: str, timeout: float, headers: dict[str, str] | None = None) -> Any:
    import urllib.request

    req = urllib.request.Request(url, headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_manifest(
    base: str = DEFAULT_OFFICIAL_BASE, timeout: float = 30.0
) -> list[OfficialChannel]:
    """下载 downit.zip 并解析其中的 downit5.cfg。"""
    url = f"{base.rstrip('/')}/{MANIFEST_FILE}"
    try:
        with _http_get(url, timeout) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            text = zf.read(MANIFEST_CFG).decode("gbk", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise TdxOfflineError(f"获取官方清单失败: {url}: {e}") from e
    return parse_downit_cfg(text)


def _expected_total(resp: Any) -> int | None:
    """从响应头推断文件总大小（200 的 Content-Length 或 206 的 Content-Range）。"""
    status = getattr(resp, "status", 200)
    if status == 206:
        cr = resp.headers.get("Content-Range")  # 形如 "bytes start-end/total"
        if cr and "/" in cr:
            total = cr.rsplit("/", 1)[-1].strip()
            if total.isdigit():
                return int(total)
        return None
    length = resp.headers.get("Content-Length")
    return int(length) if length and length.isdigit() else None


def _download(url: str, dest: Path, timeout: float, resume: bool = True) -> Path:
    """下载 url 到 dest（支持断点续传 + 核对完整性 + 原子替换）。

    若服务端给出总大小而实际字节数不足（连接中断/截断），保留 ``.part`` 供下次续传，
    不把残缺文件提升为最终文件。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    existing = tmp.stat().st_size if (resume and tmp.exists()) else 0
    headers = {"Range": f"bytes={existing}-"} if existing else {}
    try:
        with _http_get(url, timeout, headers) as resp:
            mode = "ab" if (existing and getattr(resp, "status", 200) == 206) else "wb"
            if mode == "wb":
                existing = 0
            total = _expected_total(resp)
            with open(tmp, mode) as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:  # noqa: BLE001
        raise TdxOfflineError(f"下载失败: {url}: {e}") from e
    got = tmp.stat().st_size
    if total is not None and got != total:
        raise TdxOfflineError(
            f"下载不完整: {url}: 期望 {total} 字节，实际 {got} 字节（已保留 {tmp.name} 供续传）"
        )
    tmp.replace(dest)
    return dest


def download_channel(
    channel: OfficialChannel,
    dest_dir: str | Path,
    base: str = DEFAULT_OFFICIAL_BASE,
    date: int | None = None,
    timeout: float = 300.0,
    resume: bool = True,
) -> Path:
    """下载单个通道到 dest_dir（文件名取通道末段）。"""
    url = channel.url(base, date)
    name = url.rsplit("/", 1)[-1]
    return _download(url, Path(dest_dir) / name, timeout, resume)


def download_by_type(
    type_id: int,
    dest_dir: str | Path,
    base: str = DEFAULT_OFFICIAL_BASE,
    date: int | None = None,
    channels: list[OfficialChannel] | None = None,
    timeout: float = 300.0,
    resume: bool = True,
) -> Path:
    """按类型编号下载（type 编号见 downit5.cfg）。"""
    chans = channels if channels is not None else fetch_manifest(base, timeout=30.0)
    for ch in chans:
        if ch.type == type_id:
            return download_channel(ch, dest_dir, base, date, timeout, resume)
    raise TdxOfflineError(f"未找到 type={type_id} 的官方通道")


# 常见类型编号（来自 downit5.cfg）
TYPE_2KTIC = 1
TYPE_DBF_INFO = 4
TYPE_DBF_BASE = 5
TYPE_DBF_GBBQ = 6
TYPE_VIPDOC = 7
TYPE_G3DAY = 8
TYPE_G3TIC = 9
TYPE_NEWDAY = 10
TYPE_G4DAY = 11
TYPE_G4TIC = 12


def iter_named(path: str, file: str, channels: list[OfficialChannel]) -> Iterator[OfficialChannel]:
    for ch in channels:
        if ch.path == path and ch.file == file:
            yield ch


def download_named(
    filename: str,
    dest_dir: str | Path,
    base: str = DEFAULT_OFFICIAL_BASE,
    channels: list[OfficialChannel] | None = None,
    timeout: float = 300.0,
    resume: bool = True,
) -> Path:
    """按文件名（如 ``gbbq.zip`` / ``base.zip`` / ``info.zip`` / ``vipdoc.zip``）下载。"""
    chans = channels if channels is not None else fetch_manifest(base, timeout=30.0)
    for ch in chans:
        if ch.file == filename:
            return download_channel(ch, dest_dir, base, None, timeout, resume)
    raise TdxOfflineError(f"未找到文件名 {filename} 的官方通道")
