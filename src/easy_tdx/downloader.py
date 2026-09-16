"""批量下载（增量更新 + 断点续传 + 覆盖度校验）。

按代码落盘（每只一个文件），并记录状态：
- ``_manifest.json``：每只**最新日期**（增量依据）
- ``_coverage.json``：每只**已请求覆盖区间** ``[from, to]``（用于查缺口）

特性：
- 已是最新则跳过（增量）；中断后再运行从 manifest 续传（断点续传）
- 同键重复时**以本次拉取的新数据为准**（修正历史值也能生效）
- ``verify_coverage`` 用交易日历查中间缺口；``backfill_gaps`` 补拉缺口区间
- 单文件「临时文件 + 原子替换」避免写坏
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pandas as pd

from .client import TdxClient
from .models.enums import KlineCategory, Market
from .parallel import ParallelTdx
from .validation import check_bars

__all__ = ["Downloader"]


def _today() -> int:
    return int(datetime.now().strftime("%Y%m%d"))


def _next_day(yyyymmdd: int) -> int:
    d = datetime.strptime(str(yyyymmdd), "%Y%m%d") + timedelta(days=1)
    return int(d.strftime("%Y%m%d"))


def _to_int_date(value: object) -> int:
    """把 int / date / datetime / Timestamp 归一为 YYYYMMDD。"""
    if isinstance(value, int):
        return value
    return (
        int(getattr(value, "year")) * 10000
        + int(getattr(value, "month")) * 100
        + int(getattr(value, "day"))
    )


def _normalize_days(
    trading_days: Sequence[object] | None,
) -> list[int] | None:
    if trading_days is None:
        return None
    if hasattr(trading_days, "as_ints"):  # TradingCalendar
        return list(trading_days.as_ints())
    return sorted({_to_int_date(d) for d in trading_days})


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
        rate_limit: bool = False,
        validate: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.connections = max(1, connections)
        self.host = host
        self._factory = client_factory
        self.end_date = end_date
        self.rate_limit = rate_limit
        self.validate = validate
        self.errors: dict[str, list[str]] = {}
        self.manifest_path = self.data_dir / "_manifest.json"
        self.coverage_path = self.data_dir / "_coverage.json"

    # ------------------------------------------------------------------ #
    # manifest / coverage
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

    def _load_coverage(self) -> dict[str, dict[str, int]]:
        if self.coverage_path.exists():
            try:
                raw = json.loads(self.coverage_path.read_text("utf-8"))
                return {
                    str(k): {"from": int(v["from"]), "to": int(v["to"])} for k, v in raw.items()
                }
            except Exception:
                return {}
        return {}

    def _save_coverage(self, coverage: dict[str, dict[str, int]]) -> None:
        tmp = self.coverage_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(coverage, indent=2, ensure_ascii=False), "utf-8")
        tmp.replace(self.coverage_path)

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
            # 本次拉取的数据在后，keep="last" 使其覆盖历史同键（修正值/复权变化生效）
            df = pd.concat([existing, df], ignore_index=True)
        df = (
            df.drop_duplicates(subset=["date"], keep="last")
            .sort_values("date")
            .reset_index(drop=True)
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            if fmt == "parquet":
                df.to_parquet(tmp, index=False)
            else:
                df.to_csv(tmp, index=False)
            tmp.replace(path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def _read_dates(self, key: str, fmt: str) -> set[int]:
        path = self._file(key, fmt)
        if not path.exists():
            return set()
        df = pd.read_parquet(path) if fmt == "parquet" else pd.read_csv(path)
        if df.empty or "date" not in df.columns:
            return set()
        return set(pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype(int).tolist())

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
        if fmt == "parquet" and find_spec("pyarrow") is None and find_spec("fastparquet") is None:
            raise ValueError("fmt='parquet' 需要安装 pyarrow 或 fastparquet；或改用 fmt='csv'")
        manifest = self._load_manifest()
        coverage = self._load_coverage()
        end = self.end_date or _today()
        self.errors = {}

        def work(client: TdxClient, item: tuple[Market, str]) -> tuple[str, int]:
            market, code = item
            key = f"{market.name.lower()}{code}"
            last = manifest.get(key)
            begin = _next_day(last) if last else start_date
            if begin > end:
                return key, 0
            df = client.get_bars_range(market, code, begin, end, category)
            # 无论是否取到数据，都记录「已请求覆盖到 end」（服务端可能停牌/无数据）
            cov = coverage.get(key)
            coverage[key] = {
                "from": min(cov["from"], begin) if cov else begin,
                "to": max(cov["to"], end) if cov else end,
            }
            if df.empty:
                return key, 0
            if self.validate:
                issues = check_bars(df, key)
                if issues:
                    self.errors[key] = issues
                    return key, 0
            self._append(key, df, fmt)
            max_day = int(pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").max())
            manifest[key] = max_day
            return key, len(df)

        results: dict[str, int] = {}
        with ParallelTdx(
            self.host,
            self.connections,
            rate_limit=self.rate_limit,
            client_factory=self._factory,
        ) as pool:
            for key, n in pool.map(work, list(stocks)):
                results[key] = n

        self._save_manifest(manifest)
        self._save_coverage(coverage)
        return results

    # ------------------------------------------------------------------ #
    # 覆盖度校验 / 缺口补拉
    # ------------------------------------------------------------------ #

    def verify_coverage(
        self,
        stocks: Sequence[tuple[Market, str]],
        trading_days: Sequence[object] | None = None,
        fmt: str = "csv",
    ) -> pd.DataFrame:
        """校验每只股票的覆盖情况，返回缺口报告。

        Args:
            stocks: (市场, 代码) 列表。
            trading_days: 交易日序列（int YYYYMMDD 或 date，或 ``TradingCalendar``）。
                提供时计算**应有交易日 vs 实际缺失**；不提供则只报告覆盖区间/行数。
            fmt: 本地文件格式。

        Returns:
            DataFrame 列：``key/market/code/covered_from/covered_to/rows/last_date/
            expected/missing/missing_dates``。``missing`` 为 ``None`` 表示未提供交易日历。
        """
        coverage = self._load_coverage()
        days = _normalize_days(trading_days)
        day_set = set(days) if days is not None else None

        rows: list[dict[str, object]] = []
        for market, code in stocks:
            key = f"{market.name.lower()}{code}"
            actual = self._read_dates(key, fmt)
            cov = coverage.get(key)
            rec: dict[str, object] = {
                "key": key,
                "market": int(market),
                "code": code,
                "covered_from": cov["from"] if cov else None,
                "covered_to": cov["to"] if cov else None,
                "rows": len(actual),
                "last_date": max(actual) if actual else None,
            }
            if cov is not None and day_set is not None:
                expected = {d for d in day_set if cov["from"] <= d <= cov["to"]}
                missing = sorted(expected - actual)
                rec["expected"] = len(expected)
                rec["missing"] = len(missing)
                rec["missing_dates"] = missing
            else:
                rec["expected"] = None
                rec["missing"] = None
                rec["missing_dates"] = []
            rows.append(rec)
        return pd.DataFrame(rows)

    def backfill_gaps(
        self,
        stocks: Sequence[tuple[Market, str]],
        trading_days: Sequence[object],
        category: KlineCategory = KlineCategory.DAY,
        fmt: str = "csv",
    ) -> dict[str, int]:
        """补拉覆盖区间内的**缺失交易日**（按连续缺口分段请求），返回 {key: 新增行数}。"""
        days = _normalize_days(trading_days)
        if not days:
            return {}
        pos = {d: i for i, d in enumerate(days)}
        coverage = self._load_coverage()
        self.errors = {}

        def work(client: TdxClient, item: tuple[Market, str]) -> tuple[str, int]:
            market, code = item
            key = f"{market.name.lower()}{code}"
            cov = coverage.get(key)
            if cov is None:
                return key, 0
            actual = self._read_dates(key, fmt)
            missing = [d for d in days if cov["from"] <= d <= cov["to"] and d not in actual]
            if not missing:
                return key, 0
            # 把连续（交易日相邻）的缺口归成区间
            runs: list[list[int]] = []
            cur: list[int] = []
            for d in missing:
                if cur and pos.get(d) == pos.get(cur[-1], -2) + 1:
                    cur.append(d)
                else:
                    if cur:
                        runs.append(cur)
                    cur = [d]
            if cur:
                runs.append(cur)
            added = 0
            for run in runs:
                df = client.get_bars_range(market, code, run[0], run[-1], category)
                if df.empty:
                    continue
                if self.validate:
                    issues = check_bars(df, key)
                    if issues:
                        self.errors[key] = issues
                        continue
                self._append(key, df, fmt)
                added += len(df)
            return key, added

        results: dict[str, int] = {}
        with ParallelTdx(
            self.host,
            self.connections,
            rate_limit=self.rate_limit,
            client_factory=self._factory,
        ) as pool:
            for key, n in pool.map(work, list(stocks)):
                results[key] = n
        return results
