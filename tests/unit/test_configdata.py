"""配置类加工数据解析测试（离线，使用 tests/fixtures 的真实样本）。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from easy_tdx.codec.configdata import (
    fill_block_index_with_alias,
    parse_spblock,
    parse_tdxbk,
    parse_tdxhy,
    parse_tdxstat,
    parse_tdxstat2,
    parse_tdxzs,
    parse_xgsg,
    spblock_by_name,
    unzip_zhb,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _read(name: str) -> bytes:
    return (FIX / name).read_bytes()


def test_parse_tdxstat() -> None:
    rows = parse_tdxstat(_read("tdxstat.cfg"))
    assert len(rows) >= 1
    r = rows[0]
    assert r.market == 0
    assert r.code == "000001"
    assert r.date == "20260914"
    assert r.pe_ttm == 5.29
    assert r.trend_days == 1
    assert r.change_pct == 0.94
    assert r.pe_static == 5.3939
    assert r.div_yield == 5.14
    assert len(r._fields) == 35


def test_parse_tdxstat2() -> None:
    rows = parse_tdxstat2(_read("tdxstat2.cfg"))
    assert len(rows) >= 1
    r = rows[0]
    assert r.code == "000001"
    assert r.date == "20260914"
    assert r.amount == 87607.10
    assert r.amount_prev == 97999.05
    assert r.block_index == "880829"


def test_parse_xgsg() -> None:
    rows = parse_xgsg(_read("xgsg.cfg"))
    assert len(rows) >= 1
    by_code = {r.code: r for r in rows}
    assert by_code["001246"].name == "力勤资源"
    assert by_code["001246"].date == "20260918"
    assert by_code["001246"].issue_price == 0.0  # 未定价
    assert by_code["920025"].issue_price == 4.26


def test_parse_tdxzs() -> None:
    rows = parse_tdxzs(_read("tdxzs.cfg"))
    assert rows[0].name == "轮动趋势"
    assert rows[0].code == "880081"
    assert rows[0].type == 5
    assert rows[0].sub_type == 2
    assert rows[0].ref == "轮动趋势"


def test_parse_tdxbk() -> None:
    rows = parse_tdxbk(_read("tdxbk.cfg"))
    assert {"short": "锂电池", "full": "锂电池概念"} in [
        {"short": r.short, "full": r.full} for r in rows
    ]


def test_parse_tdxhy() -> None:
    rows = parse_tdxhy(_read("tdxhy.cfg"))
    r = next(x for x in rows if x.code == "000001")
    assert r.market == 0
    assert r.tdx_hy == "T1001"
    assert r.sw_hy == "X500102"


def test_parse_spblock() -> None:
    blocks = parse_spblock(_read("spblock.dat"))
    assert blocks[0].name == "融资融券"
    assert blocks[0].codes[0] == "0000001"
    assert all(len(c) == 7 and c.isdigit() for c in blocks[0].codes)


def test_spblock_by_name() -> None:
    blocks = parse_spblock(_read("spblock.dat"))
    assert spblock_by_name(blocks, "融资融券") is blocks[0]
    assert spblock_by_name(blocks, "不存在") is None


def test_fill_block_index_with_alias() -> None:
    from easy_tdx.models.configdata import SpBlock, TdxBk, TdxZs

    blocks = [SpBlock(name="锂电池概念", codes=["0000001"]), SpBlock(name="锂电池", codes=[])]
    zs = [TdxZs(name="锂电池概念", code="880999")]
    bk = [TdxBk(short="锂电池", full="锂电池概念")]
    hit = fill_block_index_with_alias(blocks, zs, bk)
    assert hit == 2  # 直接命中 + 简称→全称二次命中
    assert blocks[0].index == "880999"
    assert blocks[1].index == "880999"


def test_unzip_zhb_roundtrip() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tdxstat.cfg", b"abc")
        zf.writestr("spblock.dat", b"xyz")
    files = unzip_zhb(buf.getvalue())
    assert files == {"tdxstat.cfg": b"abc", "spblock.dat": b"xyz"}
