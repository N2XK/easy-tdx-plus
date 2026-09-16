"""文件查询与下载命令（0x1215 / 0x1217）。"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from ..._binary import require_bytes, unpack_from
from ...codec.mac_frame import build_mac_request
from ...commands.base import BaseCommand

# 注意：实测 0x1215/0x1217 在免费 7709 主站与 MAC-EX(7727) 上均返回
# size=0/flag=1、无数据。此接口目前不可用，获取服务器文件请改用标准协议
# `TdxClient.get_report_file`（0x06b9）。
_FILELIST_MSG_ID = 0x1215
_FILEDL_MSG_ID = 0x1217

_FILENAME_LEN = 70
_FILENAME_PAD = 30


@dataclass(frozen=True)
class FileMeta:
    """文件列表查询结果。"""

    offset: int
    size: int
    flag: int
    hash: str


class FileListCmd(BaseCommand[FileMeta]):
    """查询远程文件元信息（大小、哈希等）。

    Args:
        filename: 远程文件名（GBK 编码）。
        offset: 文件偏移（默认 0）。
    """

    def __init__(self, filename: str, offset: int = 0) -> None:
        self.filename = filename
        self.offset = offset

    def build_request(self) -> bytes:
        raw_name = self.filename.encode("gbk")
        padded = (raw_name + b"\x00" * _FILENAME_LEN)[:_FILENAME_LEN]
        body = struct.pack("<I", self.offset) + padded + b"\x00" * _FILENAME_PAD
        return build_mac_request(_FILELIST_MSG_ID, body)

    def parse_response(self, body: bytes) -> FileMeta:
        require_bytes(body, 0, 4 + 4 + 1 + 32, "FileListCmd")
        offset, size, flag = unpack_from("<IIb", body, 0, "FileListCmd meta")
        raw_hash = body[9:41]
        hash_str = raw_hash.decode("ascii", errors="replace").rstrip("\x00")
        return FileMeta(offset=offset, size=size, flag=flag, hash=hash_str)


class FileDownloadCmd(BaseCommand[bytes]):
    """分段下载远程文件内容。

    Args:
        filename: 远程文件名（GBK 编码）。
        index: 分段序号（1-based）。
        offset: 字节偏移。
        size: 请求块大小（默认 30000）。
    """

    def __init__(
        self,
        filename: str,
        index: int = 1,
        offset: int = 0,
        size: int = 30000,
    ) -> None:
        self.filename = filename
        self.index = index
        self.offset = offset
        self.size = size

    def build_request(self) -> bytes:
        raw_name = self.filename.encode("gbk")
        padded = (raw_name + b"\x00" * _FILENAME_LEN)[:_FILENAME_LEN]
        body = (
            struct.pack("<III", self.index, self.offset, self.size)
            + padded
            + b"\x00" * _FILENAME_PAD
        )
        return build_mac_request(_FILEDL_MSG_ID, body)

    def parse_response(self, body: bytes) -> bytes:
        # 失败/无数据时服务端只回 8~9 字节头部（flag=1、size=0）；不返回垃圾字节
        if len(body) <= 8:
            return b""
        return body[8:]
