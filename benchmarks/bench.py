"""性能基准脚本。

用法::

    python benchmarks/bench.py            # 离线基准（合成数据，无需网络）
    python benchmarks/bench.py --live     # 追加联网基准（真实服务器）
    python benchmarks/bench.py --live --host 180.153.18.170 --requests 50

离线档可复现、适合回归对比；联网档用于评估实测延迟与并发吞吐。
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable

import numpy as np
import pandas as pd


def _synth_bars(n: int = 5000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 10 + np.cumsum(rng.normal(0, 0.05, n))
    high = close + rng.uniform(0, 0.2, n)
    low = close - rng.uniform(0, 0.2, n)
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "vol": rng.integers(1000, 100000, n).astype(float),
            "amount": close * 1e5,
        }
    )


def _timeit(fn: Callable[[], object], repeat: int = 5) -> tuple[float, float]:
    """返回 (最快耗时秒, 中位耗时秒)。"""
    samples: list[float] = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return min(samples), statistics.median(samples)


def _row(name: str, fast: float, median: float) -> str:
    return f"{name:<34} min={fast * 1000:8.2f} ms  median={median * 1000:8.2f} ms"


def bench_offline(repeat: int) -> None:
    from easy_tdx.derive import add_indicators
    from easy_tdx.derive.formula import evaluate

    bars = _synth_bars()
    print(f"[offline] 合成 {len(bars)} 根日线")

    f, m = _timeit(lambda: add_indicators(bars), repeat)
    print("  " + _row("add_indicators (MA/MACD/KDJ/BOLL/RSI)", f, m))

    formula = "DIF: EMA(CLOSE,12)-EMA(CLOSE,26); DEA: EMA(DIF,9); MACD: (DIF-DEA)*2;"
    f, m = _timeit(lambda: evaluate(formula, bars), repeat)
    print("  " + _row("formula MACD", f, m))

    f, m = _timeit(lambda: evaluate("Z: ZIG(CLOSE,5); P: PEAK(CLOSE,5,1);", bars), repeat)
    print("  " + _row("formula ZIG/PEAK", f, m))


def bench_live(host: str | None, requests: int, connections: int) -> None:
    from easy_tdx import KlineCategory, Market, ParallelTdx, TdxClient

    print(f"[live] host={host or 'best'} requests={requests} connections={connections}")

    client = TdxClient.from_best_host(hosts=[host] if host else None)
    with client:
        f, m = _timeit(lambda: client.get_security_quotes([(Market.SH, "600519")]), 5)
        print("  " + _row("get_security_quotes x1", f, m))

        f, m = _timeit(lambda: client.get_bars(Market.SH, "600519", KlineCategory.DAY, 0, 800), 5)
        print("  " + _row("get_bars 800 日线", f, m))

    codes = [f"{600000 + i:06d}" for i in range(requests)]
    t0 = time.perf_counter()
    with ParallelTdx(host, connections=connections) as pool:
        pool.map(lambda c, code: c.get_security_quotes([(Market.SH, code)]), codes)
    elapsed = time.perf_counter() - t0
    print(
        f"  {'ParallelTdx 并发报价':<34} {requests} req in {elapsed:.2f}s "
        f"= {requests / elapsed:.1f} req/s"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="easy_tdx 性能基准")
    parser.add_argument("--live", action="store_true", help="追加联网基准")
    parser.add_argument("--host", default=None, help="指定服务器（默认最佳主机）")
    parser.add_argument("--repeat", type=int, default=5, help="离线重复次数")
    parser.add_argument("--requests", type=int, default=50, help="联网并发请求数")
    parser.add_argument("--connections", type=int, default=8, help="并发连接数")
    args = parser.parse_args()

    bench_offline(args.repeat)
    if args.live:
        bench_live(args.host, args.requests, args.connections)


if __name__ == "__main__":
    main()
