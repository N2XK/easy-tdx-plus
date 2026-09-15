"""easy-tdx 异常层次"""


class TdxError(Exception):
    """所有 easy-tdx 异常的基类"""


class TdxConnectionError(TdxError):
    """TCP 连接失败或超时"""


class TdxDecodeError(TdxError):
    """响应报文解析失败"""


class TdxCommandError(TdxError):
    """命令执行失败（服务器返回错误）"""


class TdxFileNotFoundError(TdxError):
    """本地数据文件不存在"""


class TdxOfflineError(TdxError):
    """离线数据读取失败（路径未配置、文件格式错误等）"""


class TdxValidationError(TdxError):
    """响应数据未通过语义校验（字段越界、OHLC 关系非法等）"""
