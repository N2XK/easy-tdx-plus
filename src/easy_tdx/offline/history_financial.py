"""历史财务数据读取（gpcw*.dat / gpcw*.zip 文件）。"""

import zipfile
from pathlib import Path

import pandas as pd

from ..codec.financial import parse_financial_dat
from ..exceptions import TdxFileNotFoundError, TdxOfflineError
from ..models.enums import Market
from ..models.finance import FinancialRecord


def read_history_financial(filepath: str | Path) -> list[FinancialRecord]:
    """从本地 gpcw*.dat 或 gpcw*.zip 文件读取历史财务数据。

    复用 codec/financial.py 的 parse_financial_dat() 解析二进制格式。

    Args:
        filepath: .dat 或 .zip 文件路径。

    Returns:
        FinancialRecord 列表。
    """
    filepath = Path(filepath)
    if not filepath.is_file():
        raise TdxFileNotFoundError(f"历史财务数据文件不存在: {filepath}")

    if filepath.suffix.lower() == ".zip":
        data = _read_from_zip(filepath)
    else:
        data = filepath.read_bytes()

    raw_records = parse_financial_dat(data)
    results: list[FinancialRecord] = []
    for code, market_byte, report_date, fields in raw_records:
        value = market_byte[0] if isinstance(market_byte, (bytes, bytearray)) else int(market_byte)
        try:
            market = Market(value)
        except ValueError:
            market = Market.SZ  # 默认深圳
        results.append(
            FinancialRecord(
                code=code,
                market=market,
                report_date=report_date,
                fields=fields,
            )
        )
    return results


def read_history_financial_df(filepath: str | Path) -> pd.DataFrame:
    """从本地 gpcw*.dat / .zip 读取历史财务并转 DataFrame。

    列为 ``code / market / report_date`` 加位置字段 ``f0..fN``（字段含义随报告期
    不同，见对应 gpcw 的字段定义）。``report_date`` 可用于构造 point-in-time 面板。
    """
    records = read_history_financial(filepath)
    if not records:
        return pd.DataFrame(columns=["code", "market", "report_date"])
    width = max((len(r.fields) for r in records), default=0)
    rows: list[dict[str, object]] = []
    for r in records:
        row: dict[str, object] = {
            "code": r.code,
            "market": int(r.market),
            "report_date": r.report_date,
        }
        for i in range(width):
            row[f"f{i}"] = r.fields[i] if i < len(r.fields) else None
        rows.append(row)
    return pd.DataFrame(rows)


def read_financial_history_panel(
    source: str | Path | list[str | Path],
    codes: list[str] | None = None,
) -> pd.DataFrame:
    """把多季度 gpcw 文件拼成 point-in-time 财务面板。

    Args:
        source: 目录（会读取其中全部 ``gpcw*.zip`` / ``gpcw*.dat``）或文件路径列表。
        codes: 仅保留这些代码。

    Returns:
        含 ``code / market / report_date / f0..fN`` 的面板，按 (code, report_date) 升序。
    """
    if isinstance(source, (str, Path)) and Path(source).is_dir():
        base = Path(source)
        paths = sorted(base.glob("gpcw*.zip")) + sorted(base.glob("gpcw*.dat"))
    elif isinstance(source, (str, Path)):
        paths = [Path(source)]
    else:
        paths = [Path(p) for p in source]

    frames = [read_history_financial_df(p) for p in paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=["code", "market", "report_date"])
    panel = pd.concat(frames, ignore_index=True)
    if codes:
        panel = panel[panel["code"].isin(set(codes))]
    return panel.sort_values(["code", "report_date"]).reset_index(drop=True)


def _read_from_zip(zip_path: Path) -> bytes:
    """从 zip 中提取 .dat 文件内容。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".dat"):
                    return zf.read(name)
            raise TdxOfflineError(f"zip 中未找到 .dat 文件: {zip_path}")
    except zipfile.BadZipFile as e:
        raise TdxOfflineError(f"无效的 zip 文件: {zip_path}") from e
