"""可插拔数据落库接口。

核心包只依赖 pandas；DuckDB/ClickHouse 通过可选依赖使用，避免把数据库运行时
塞进行情客户端。所有 sink 都保留 provenance，方便增量同步和审计。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from .provenance import DataProvenance, get_provenance


class StorageError(RuntimeError):
    """存储层错误。"""


class StorageSink(Protocol):
    """统一的 DataFrame 写入接口。"""

    def write(
        self,
        table: str,
        frame: pd.DataFrame,
        *,
        provenance: DataProvenance | None = None,
        mode: str = "append",
    ) -> int: ...


def _with_metadata(frame: pd.DataFrame, provenance: DataProvenance | None) -> pd.DataFrame:
    out = frame.copy()
    prov = provenance or get_provenance(frame)
    if prov is not None:
        values = prov.to_dict()
        for key, value in values.items():
            out[f"_meta_{key}"] = value
    return out


class ParquetSink:
    """按表名写入 Parquet 文件，使用临时文件保证原子替换。"""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)

    def write(
        self,
        table: str,
        frame: pd.DataFrame,
        *,
        provenance: DataProvenance | None = None,
        mode: str = "append",
    ) -> int:
        if mode not in {"append", "overwrite"}:
            raise ValueError("mode must be append or overwrite")
        if not table or Path(table).name != table:
            raise ValueError("table must be a simple file name")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{table}.parquet"
        out = _with_metadata(frame, provenance)
        if mode == "append" and path.exists():
            try:
                out = pd.concat([pd.read_parquet(path), out], ignore_index=True)
            except Exception as exc:  # noqa: BLE001
                raise StorageError(f"读取既有 Parquet 失败: {path}") from exc
        fd, tmp_name = tempfile.mkstemp(prefix=f".{table}.", suffix=".parquet", dir=self.root)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            out.to_parquet(tmp, index=False)
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001
            tmp.unlink(missing_ok=True)
            raise StorageError(f"写入 Parquet 失败: {path}") from exc
        return len(frame)


class DuckDBSink:
    """DuckDB sink；需要额外安装 ``duckdb``。"""

    def __init__(self, database: str | os.PathLike[str]) -> None:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise StorageError("DuckDB sink 需要安装 easy-tdx-plus[duckdb]") from exc
        self._duckdb = duckdb
        self.database = str(database)
        self._conn = duckdb.connect(self.database)

    def close(self) -> None:
        self._conn.close()

    def write(
        self,
        table: str,
        frame: pd.DataFrame,
        *,
        provenance: DataProvenance | None = None,
        mode: str = "append",
    ) -> int:
        if not table.replace("_", "").isalnum() or not table[0].isalpha():
            raise ValueError("table must be an SQL identifier")
        out = _with_metadata(frame, provenance)
        self._conn.register("_easy_tdx_frame", out)
        try:
            if mode == "overwrite":
                self._conn.execute(
                    f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM _easy_tdx_frame'
                )
            elif mode == "append":
                exists = self._conn.execute(
                    "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
                ).fetchone()[0]
                if exists:
                    self._conn.execute(f'INSERT INTO "{table}" SELECT * FROM _easy_tdx_frame')
                else:
                    self._conn.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _easy_tdx_frame')
            else:
                raise ValueError("mode must be append or overwrite")
        finally:
            self._conn.unregister("_easy_tdx_frame")
        return len(frame)


class ClickHouseSink:
    """ClickHouse sink 的可选适配点。

    通过 ``clickhouse-connect`` 注入客户端，避免核心包强制依赖具体驱动。
    """

    def __init__(self, client: Any) -> None:
        if not hasattr(client, "insert_df"):
            raise TypeError("client must provide insert_df(table, dataframe)")
        self.client = client

    def write(
        self,
        table: str,
        frame: pd.DataFrame,
        *,
        provenance: DataProvenance | None = None,
        mode: str = "append",
    ) -> int:
        if mode != "append":
            raise ValueError("ClickHouseSink only supports append")
        self.client.insert_df(table, _with_metadata(frame, provenance))
        return len(frame)


__all__ = ["StorageError", "StorageSink", "ParquetSink", "DuckDBSink", "ClickHouseSink"]
