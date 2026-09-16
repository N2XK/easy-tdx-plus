"""离线数据读取模块 —— 从本地通达信安装目录读取数据文件。"""

from .block import CustomerBlock, read_block_dat, read_customer_blocks
from .daily_bar import find_daily_bar_file, read_daily_bars, read_daily_bars_df
from .ex_daily_bar import ExDailyBar, read_ex_daily_bars, read_ex_daily_bars_df
from .finders import find_5min_bar_file, find_lc1_bar_file, find_lc5_bar_file
from .gbbq import GbbqRecord, read_gbbq
from .history_financial import (
    read_financial_history_panel,
    read_history_financial,
    read_history_financial_df,
)
from .htc import HtcEntry, HtcHeader, iter_htc, read_htc
from .min_bar import read_5min_bars, read_5min_bars_df, read_lc_min_bars, read_lc_min_bars_df
from .official import (
    DEFAULT_OFFICIAL_BASE,
    OfficialChannel,
    download_by_type,
    download_channel,
    download_named,
    fetch_manifest,
    parse_downit_cfg,
)
from .paths import detect_tdx_home, resolve_vipdoc

__all__ = [
    # 路径
    "detect_tdx_home",
    "resolve_vipdoc",
    # 日线
    "read_daily_bars",
    "read_daily_bars_df",
    "find_daily_bar_file",
    # 分钟线
    "read_5min_bars",
    "read_5min_bars_df",
    "read_lc_min_bars",
    "read_lc_min_bars_df",
    "find_5min_bar_file",
    "find_lc1_bar_file",
    "find_lc5_bar_file",
    # 扩展市场
    "ExDailyBar",
    "read_ex_daily_bars",
    "read_ex_daily_bars_df",
    # 板块
    "CustomerBlock",
    "read_block_dat",
    "read_customer_blocks",
    # 股本变迁
    "GbbqRecord",
    "read_gbbq",
    # 历史财务
    "read_history_financial",
    "read_history_financial_df",
    "read_financial_history_panel",
    # 官方下载（tdx.com.cn）
    "OfficialChannel",
    "parse_downit_cfg",
    "fetch_manifest",
    "download_channel",
    "download_by_type",
    "download_named",
    "DEFAULT_OFFICIAL_BASE",
    # 官方分笔容器 .htc
    "HtcEntry",
    "HtcHeader",
    "iter_htc",
    "read_htc",
]
