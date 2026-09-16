"""演示：技术指标（MACD / KDJ / BOLL / RSI / MA / 量比）。

在 easy_tdx 取到的日线上直接计算常用指标（纯计算，无额外数据源）。

使用客户端：TdxClient
"""

from easy_tdx import Market, TdxClient, add_indicators, boll


def main() -> None:
    with TdxClient.from_best_host() as c:
        bars = c.get_bars_range(Market.SH, "600519", 20250101, 20991231)
    print("日线行数:", len(bars))

    # 一次性追加常用指标
    df = add_indicators(bars, ma_periods=[5, 20], rsi_periods=[6, 12])
    cols = ["date", "close", "ma5", "ma20", "dif", "dea", "macd", "k", "d", "j", "rsi6"]
    print(df[cols].tail(3).to_string(index=False))

    # 也可以单独调用
    print("\nBOLL 末行:", boll(df["close"]).iloc[-1].round(2).to_dict())


if __name__ == "__main__":
    main()
