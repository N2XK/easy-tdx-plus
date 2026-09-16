"""管理命令：ping, caps, version。"""

from __future__ import annotations

import click


@click.command()
@click.option("--timeout", default=5.0, help="测速超时（秒）")
@click.option("--caps", "with_caps", is_flag=True, help="附加探测各服务器分项能力")
@click.option("--limit", default=6, type=int, help="--caps 时探测的主机数")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def ping(timeout: float, with_caps: bool, limit: int, use_table: bool, output_fmt: str) -> None:
    """测量通达信服务器延迟。

    示例：

      easy-tdx ping

      easy-tdx ping --timeout 3 --table

      easy-tdx ping --caps            # 附带各服务器支持的能力
    """
    import pandas as pd

    from ..capabilities import FEATURES, probe_capabilities
    from ..transport.sync import ping_all, ping_mac_all
    from .output import print_output

    fmt = "table" if use_table else output_fmt

    click.echo("正在测速标准服务器...", err=True)
    std_results = ping_all(timeout=timeout)
    click.echo("正在测速MAC服务器...", err=True)
    mac_results = ping_mac_all(timeout=timeout)

    caps_by_host: dict[str, dict[str, bool]] = {}
    if with_caps:
        for host, _latency in std_results[:limit]:
            caps_by_host[host] = probe_capabilities(host, timeout=timeout)

    rows: list[dict[str, object]] = []
    for host, latency in std_results:
        row: dict[str, object] = {
            "group": "standard",
            "host": host,
            "latency_ms": round(latency * 1000, 1),
        }
        if with_caps:
            caps = caps_by_host.get(host, {})
            row.update({f: caps.get(f) for f in FEATURES})
        rows.append(row)
    for host, latency in mac_results:
        rows.append({"group": "mac", "host": host, "latency_ms": round(latency * 1000, 1)})

    df = pd.DataFrame(rows)
    print_output(df, fmt)


@click.command()
@click.option("--host", default=None, help="只探测指定主机（默认探测最快的若干台）")
@click.option("--timeout", default=6.0, help="探测超时（秒）")
@click.option("--limit", default=6, type=int, help="探测主机数")
@click.option("--refresh", is_flag=True, help="忽略缓存，强制重新探测")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def caps(
    host: str | None, timeout: float, limit: int, refresh: bool, use_table: bool, output_fmt: str
) -> None:
    """探测服务器分项能力（quotes/kline/transaction/finance/xdxr/security_list）。

    示例：

      easy-tdx caps --table

      easy-tdx caps --host 59.36.5.11

      easy-tdx caps --limit 10 --refresh
    """
    import pandas as pd

    from ..capabilities import FEATURES, probe_capabilities
    from ..transport.sync import ping_all
    from .output import print_output

    fmt = "table" if use_table else output_fmt

    if host:
        hosts = [host]
    else:
        click.echo("正在测速以挑选主机...", err=True)
        hosts = [h for h, _ in ping_all(timeout=timeout)[:limit]]

    rows = []
    for h in hosts:
        c = probe_capabilities(h, timeout=timeout, refresh=refresh)
        row: dict[str, object] = {"host": h}
        row.update({f: c.get(f) for f in FEATURES})
        row["ok_count"] = sum(1 for f in FEATURES if c.get(f))
        rows.append(row)
    print_output(pd.DataFrame(rows), fmt)


@click.command()
def version() -> None:
    """显示版本号。"""
    from .. import __version__

    click.echo(f"easy-tdx {__version__}")
