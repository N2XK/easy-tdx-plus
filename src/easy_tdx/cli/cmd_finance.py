"""财务数据命令。"""

from __future__ import annotations

import click


@click.command("f10")
@click.argument("market")
@click.argument("code")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def f10(market: str, code: str, use_table: bool, output_fmt: str) -> None:
    """获取标准协议财务数据。

    示例：

      easy-tdx f10 SZ 000001

      easy-tdx f10 SZ 000001 --table
    """
    from ..client import TdxClient
    from ..models import Market
    from .output import print_output
    from .parsers import parse_market

    fmt = "table" if use_table else output_fmt
    with TdxClient.from_best_host(require=["finance"]) as client:
        df = client.get_finance_info(Market(parse_market(market)), code)
    print_output(df, fmt)


@click.command("fund-flow")
@click.argument("market")
@click.argument("code")
@click.option("--start", default=0, type=int, help="起始偏移")
@click.option("--count", default=30, type=int, help="请求数量")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def fund_flow(
    market: str,
    code: str,
    start: int,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """获取历史资金流向。

    示例：

      easy-tdx fund-flow SZ 000001
    """
    from ..client import TdxClient
    from ..models import Market
    from .output import print_output
    from .parsers import parse_market

    fmt = "table" if use_table else output_fmt
    with TdxClient.from_best_host(require=["kline", "transaction"]) as client:
        df = client.get_history_fund_flow(Market(parse_market(market)), code, start, count)
    print_output(df, fmt)
