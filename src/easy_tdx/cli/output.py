"""CLI 输出格式化：JSON（默认）、表格、CSV。"""

from __future__ import annotations

import click
import pandas as pd


def format_output(df: pd.DataFrame, fmt: str = "json") -> str:
    """将 DataFrame 格式化为指定输出格式。"""
    if df.empty:
        return "[]" if fmt == "json" else ""

    if fmt == "json":
        result: str = df.to_json(orient="records", force_ascii=False, date_format="iso")
        return result
    if fmt == "csv":
        return str(df.to_csv(index=False))
    if fmt == "table":
        return _render_table(df)
    raise click.UsageError(f"不支持的输出格式: {fmt}")


def print_output(df: pd.DataFrame, fmt: str = "json") -> None:
    """格式化并输出 DataFrame 到 stdout。"""
    text = format_output(df, fmt)
    if text:
        click.echo(text)


def _render_table(df: pd.DataFrame) -> str:
    """将 DataFrame 渲染为人类可读的文本表格。"""
    if df.empty:
        return "(无数据)"

    display_df = df.copy()
    for col in display_df.columns:
        if display_df[col].dtype == object:
            display_df[col] = display_df[col].astype(str).str.slice(0, 30)

    try:
        import tabulate

        return str(tabulate.tabulate(display_df, headers="keys", tablefmt="grid", showindex=False))
    except ImportError:
        lines: list[str] = []
        cols = list(display_df.columns)
        header = " | ".join(str(c) for c in cols)
        sep = "-+-".join("-" * min(len(str(c)), 30) for c in cols)
        lines.append(header)
        lines.append(sep)
        for _, row in display_df.iterrows():
            line = " | ".join(str(v)[:30] for v in row.values)
            lines.append(line)
        return "\n".join(lines)
