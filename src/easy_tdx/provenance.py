"""数据来源和口径元数据。

TDX 返回值经常混合服务端原始字段和客户端推导字段。这个模块提供一个轻量
的、可序列化的描述，供 DataFrame.attrs、存储层和下游审计使用。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DataProvenance:
    """描述一批数据的来源、时间点和计算口径。"""

    source: str
    as_of: str | None = None
    point_in_time: bool = False
    is_approximate: bool = False
    calculation_method: str | None = None
    server_host: str | None = None
    request_id: str | None = None
    schema_version: str = "1"
    created_at: str | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            object.__setattr__(
                self,
                "created_at",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def attach_provenance(frame: Any, provenance: DataProvenance) -> Any:
    """将 provenance 附加到 pandas DataFrame，不改变数据列。"""

    attrs = getattr(frame, "attrs", None)
    if attrs is not None:
        attrs["provenance"] = provenance.to_dict()
    return frame


def get_provenance(frame: Any) -> DataProvenance | None:
    """从 DataFrame.attrs 读取 provenance。"""

    raw = getattr(frame, "attrs", {}).get("provenance")
    if not isinstance(raw, dict) or "source" not in raw:
        return None
    fields = {field: raw[field] for field in DataProvenance.__dataclass_fields__ if field in raw}
    return DataProvenance(**fields)
