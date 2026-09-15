"""批量下载（增量更新 + 断点续传）。

按代码落盘（每只一个文件），并用 ``_manifest.json`` 记录每只最新日期：
- 已是最新则跳过（增量）
- 中途中断后再次运行会从 manifest 续传（断点续传）
- 单文件采用「临时文件 + 原子替换」避免写坏
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from .client import TdxClient
from .models.enums import KlineCategory, Market
from .parallel import ParallelTdx

__all__ = ["Downloader"]


def _today() -> int:
    return int(datetime.now().strftime("%Y%m%d"))


def _next_day(yyyymmdd: int) -> int:
    d = datetime.strptime(str(yyyymmdd), "%Y%m%d") + timedelta(days=1)
    return int(d.strftime("%Y%m%d"))


class Downloader:
    """批量日线下载器。

    Args:
        data_dir: 落盘目录。
        connections: 并发连接数（1 表示串行）。
        host: 服务器地址（None 用默认）。
        client_factory: 自定义客户端工厂（测试注入）。
        end_date: 结束日期 YYYYMMDD（默认今天）。
    """

    def __init__(
        self,
        data_dir: str | Path,
        connections: int = 4,
        host: str | None = None,
        client_factory: Callable[[], TdxClient] | None = None,
        end_date: int | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.connections = max(1, connections)
        self.host = host
        self._factory = client_factory
        self.end_date = end_date
        self.manifest_path = self.data_dir / "_manifest.json"

    # ------------------------------------------------------------------ #
    # manifest
    # ------------------------------------------------------------------ #

    def _load_manifest(self) -> dict[str, int]:
        if self.manifest_path.exists():
            try:
                raw = json.loads(self.manifest_path.read_text("utf-8"))
                return {str(k): int(v) for k, v in raw.items()}
            except Exception:
                return {}
        return {}

    def _save_manifest(self, manifest: dict[str, int]) -> None:
        tmp = self.manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(self.manifest_path)

    # ------------------------------------------------------------------ #
    # 落盘
    # ------------------------------------------------------------------ #

    def _file(self, key: str, fmt: str) -> Path:
        return self.data_dir / f"{key}.{fmt}"

    def _append(self, key: str, df: pd.DataFrame, fmt: str) -> None:
        path = self._file(key, fmt)
        if path.exists():
            existing = pd.read_parquet(path) if fmt == "parquet" else pd.read_csv(path)
            existing["date"] = pd.to_datetime(existing["date"])
            df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        if fmt == "parquet":
            df.to_parquet(tmp, index=False)
        else:
            df.to_csv(tmp, index=False)
        tmp.replace(path)

    # ------------------------------------------------------------------ #
    # 下载
    # ------------------------------------------------------------------ #

    def download_daily(
        self,
        stocks: Sequence[tuple[Market, str]],
        start_date: int = 19900101,
        category: KlineCategory = KlineCategory.DAY,
        fmt: str = "csv",
    ) -> dict[str, int]:
        """增量下载日线，返回 {key: 本次新增行数}。"""
        if fmt not in ("csv", "parquet"):
            raise ValueError("fmt 必须是 'csv' 或 'parquet'")
        manifest = self._load_manifest()
        end = self.end_date or _today()

        def work(client: TdxClient, item: tuple[Market, str]) -> tuple[str, int]:
            market, code = item
            key = f"{market.name.lower()}{code}"
            last = manifest.get(key)
            begin = _next_day(last) if last else start_date
            if begin > end:
                return key, 0
            df = client.get_bars_range(market, code, begin, end, category)
            if df.empty:
                return key, 0
            self._append(key, df, fmt)
            max_day = int(pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").max())
            manifest[key] = max_day
            return key, len(df)

        results: dict[str, int] = {}
        with ParallelTdx(self.host, self.connections, client_factory=self._factory) as pool:
            for key, n in pool.map(work, list(stocks)):
                results[key] = n

        self._save_manifest(manifest)
        return results
