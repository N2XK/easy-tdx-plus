"""MAC 多日分时 0x123E 解析测试（离线，合成体）。"""

from __future__ import annotations

import struct

from easy_tdx.mac.commands.tick_charts import TickChartsCmd


def _body() -> bytes:
    b = bytearray(71)
    struct.pack_into("<H22s", b, 0, 1, b"600519")
    struct.pack_into("<5I", b, 24, 20260916, 20260915, 0, 0, 0)
    struct.pack_into("<5f", b, 44, 1272.75, 1277.96, 0.0, 0.0, 0.0)
    # count=2, send_last=1, page_size=3, total=4（今日 1 条 + 昨日 3 条）
    struct.pack_into("<HBHH", b, 64, 2, 1, 3, 4)

    ticks = [
        (640, 10.0, 10.1, 5, 0),  # 今日(新→旧排在前) 单条
        (570, 11.0, 11.0, 1, 0),  # 昨日
        (571, 11.1, 11.0, 2, 0),
        (0xFFFF, 0.0, 0.0, 0, 0),  # 无效填充（minutes 越界，应跳过）
    ]
    for minutes, price, avg, vol, res in ticks:
        b += struct.pack("<HffHH", minutes, price, avg, vol, res)

    b += b"\x00" * 120  # 尾部元数据（测试不校验内容）
    return bytes(b)


def test_tick_charts_groups_and_skips_padding() -> None:
    chart = TickChartsCmd(1, "600519", None, 2).parse_response(_body())
    assert [d.date.isoformat() for d in chart.charts] == ["2026-09-16", "2026-09-15"]
    assert len(chart.charts[0].ticks) == 1
    # 昨日 3 条中 1 条为无效分钟，跳过 -> 2 条
    assert len(chart.charts[1].ticks) == 2
    assert chart.charts[1].ticks[0].time.strftime("%H:%M") == "09:30"
