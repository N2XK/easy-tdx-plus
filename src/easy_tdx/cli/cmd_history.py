"""历史逐笔 / 交易日历命令。"""

from __future__ import annotations

import click


@click.command("history-transaction")
@click.argument("market")
@click.argument("code")
@click.argument("date", type=int)
@click.option("--count", default=800, type=int, help="单页条数（自动翻页至结束）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def history_transaction(
    market: str,
    code: str,
    date: int,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """获取某历史日**全部**逐笔成交（自动分页）。

    MARKET: SZ/SH/BJ；DATE: YYYYMMDD

    示例：

      easy-tdx history-transaction SZ 000001 20240102

      easy-tdx history-transaction SZ 000001 20240102 --table
    """
    from ..client import TdxClient
    from ..models.enums import Market
    from .output import print_output
    from .parsers import parse_market

    fmt = "table" if use_table else output_fmt
    mkt = Market(parse_market(market))
    with TdxClient.from_best_host() as client:
        df = client.get_history_transaction_all(mkt, code, date, count=count)
    print_output(df, fmt)


@click.command("trading-calendar")
@click.option("--start", default=19900101, type=int, help="起始日期 YYYYMMDD")
@click.option("--end", default=None, type=int, help="结束日期 YYYYMMDD（默认今天）")
@click.option("--days", default=0, type=int, help="仅显示最近 N 个交易日（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def trading_calendar(
    start: int,
    end: int | None,
    days: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """列出一段区间内的交易日（由上证指数日线构建，含节假日）。

    示例：

      easy-tdx trading-calendar --days 10 --table

      easy-tdx trading-calendar --start 20240101 --end 20240131
    """
    import pandas as pd

    from ..client import TdxClient
    from .output import print_output

    fmt = "table" if use_table else output_fmt
    with TdxClient.from_best_host() as client:
        cal = client.get_trading_calendar(start, end)
    picked = cal.recent(days) if days > 0 else cal.days
    df = pd.DataFrame({"date": [d.isoformat() for d in picked]})
    print_output(df, fmt)
