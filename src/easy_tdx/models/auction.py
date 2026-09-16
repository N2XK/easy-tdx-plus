"""集合竞价过程快照条目（标准协议 0x056a）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class AuctionPoint:
    """集合竞价过程中的一个秒级快照。"""

    time: time
    price: float
    matched: int  # 虚拟匹配量
    unmatched: int  # 未匹配量（带方向，正为买方剩余）
