"""异动数据查询（0x1237）。"""

import struct
from datetime import time

from ..._binary import unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand
from ..models import UnusualItem


def _describe_unusual(unusual_type: int, data: bytes) -> tuple[str, str]:
    """根据异动类型解析描述和数值。"""
    if len(data) < 13:
        return "", ""
    v1, v2, v3, v4 = struct.unpack_from("<B2fI", data)

    if unusual_type == 0x03:
        desc = f"主力{'买入' if v1 == 0x00 else '卖出'}"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x04:
        desc = "加速拉升"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x05:
        desc = "加速下跌"
        val = ""
    elif unusual_type == 0x06:
        desc = "低位反弹"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x07:
        desc = "高位回落"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x08:
        desc = "撑杆跳高"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x09:
        desc = "平台跳水"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x0A:
        desc = f"单笔冲{'跌' if v2 < 0 else '涨'}"
        val = f"{v2 * 100:.2f}%"
    elif unusual_type == 0x0B:
        direction = "平" if v3 == 0 else "跌" if v3 < 0 else "涨"
        desc = f"区间放量{direction}"
        val = f"{v2:.1f}倍" + ("" if v3 == 0 else f"{v3 * 100:.2f}%")
    elif unusual_type == 0x0C:
        desc = "区间缩量"
        val = ""
    elif unusual_type == 0x10:
        desc = "大单托盘"
        val = f"{v4:.2f}/{v3:.2f}"
    elif unusual_type == 0x11:
        desc = "大单压盘"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x12:
        desc = "大单锁盘"
        val = ""
    elif unusual_type == 0x13:
        desc = "竞价试买"
        val = f"{v2:.2f}/{v3:.2f}"
    elif unusual_type == 0x14:
        direction = "涨" if v1 == 0x00 else "跌"
        if len(data) >= 10:
            sub_type, v2_alt, v3_alt = struct.unpack_from("<Bff", data, 1)
        else:
            sub_type, v2_alt, v3_alt = 0, 0.0, 0.0
        if sub_type == 0x01:
            desc = f"逼近{direction}停"
        elif sub_type == 0x02:
            desc = f"封{direction}停板"
        elif sub_type == 0x04:
            desc = f"封{direction}大减"
        elif sub_type == 0x05:
            desc = f"打开{direction}停"
        else:
            desc = f"涨跌停({direction})"
        val = f"{v2_alt:.2f}/{v3_alt:.2f}"
    else:
        desc = f"异动类型{unusual_type:#04x}"
        val = ""

    return desc, val


class UnusualCmd(BaseCommand[list[UnusualItem]]):
    """查询异动数据。

    Parameters
    ----------
    market : int
        市场代码。
    start : int
        起始偏移量。
    count : int
        请求数量（最大 600）。
    """

    def __init__(self, market: int, start: int = 0, count: int = 600) -> None:
        self._market = market
        self._start = start
        self._count = min(count, 600)

    def build_request(self) -> bytes:
        # H:market, H:start, 2x padding, H:count, 2x padding, 5×H monitoring params
        body = struct.pack(
            "<HH2xH2xH5H",
            self._market,
            self._start,
            self._count,
            1,  # monitor param 1
            200,  # monitor param 2
            30,  # monitor param 3
            40,  # monitor param 4
            50,  # monitor param 5
            200,  # monitor param 6
        )
        return build_mac_request(0x1237, body)

    def parse_response(self, body: bytes) -> list[UnusualItem]:
        (count,) = unpack_from("<H", body, 0, "unusual count")

        results: list[UnusualItem] = []
        for i in range(count):
            offset = 2 + i * 32
            if offset + 32 > len(body):
                break

            market, code_raw, _, unusual_type, _, index, _z = unpack_from(
                "<H6sBBBHH", body, offset, f"unusual record[{i}]"
            )

            desc, value = _describe_unusual(unusual_type, body[offset + 15 : offset + 28])

            hour, minute_sec = unpack_from("<BH", body, offset + 29, f"unusual time[{i}]")

            results.append(
                UnusualItem(
                    index=index,
                    market=market,
                    code=code_raw.decode("gbk", errors="replace").rstrip("\x00"),
                    name="",  # populated below from text section
                    time=time(hour, minute_sec // 100, minute_sec % 100),
                    desc=desc,
                    value=value,
                    unusual_type=unusual_type,
                )
            )

        # Text section: stock names in GBK, comma-separated
        binary_length = 2 + count * 32
        text_bytes = body[binary_length:]
        text_list = text_bytes.decode("gbk", errors="ignore").strip(",").split(",")

        # Fill names from text section
        populated: list[UnusualItem] = []
        for i, item in enumerate(results):
            name = text_list[i] if i < len(text_list) else ""
            populated.append(
                UnusualItem(
                    index=item.index,
                    market=item.market,
                    code=item.code,
                    name=name,
                    time=item.time,
                    desc=item.desc,
                    value=item.value,
                    unusual_type=item.unusual_type,
                )
            )

        return populated
