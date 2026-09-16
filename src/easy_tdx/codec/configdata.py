"""配置类加工数据解析（zhb.zip 成员文件 / tdxhy.cfg）。

纯函数、无 IO。字段语义参考 injoyai/tdx（MIT）。
"""

from __future__ import annotations

import io
import zipfile

from ..models.configdata import (
    NamedBlock,
    SpBlock,
    TdxAdr,
    TdxAhRate,
    TdxBjCode,
    TdxBk,
    TdxBroker,
    TdxChain,
    TdxCodeName,
    TdxConcept,
    TdxHy,
    TdxIndexName,
    TdxIndustryNode,
    TdxStat,
    TdxStat2,
    TdxStockPinyin,
    TdxXgsg,
    TdxZs,
)

_FIELD_SEP = "|"


def _decode_gbk(data: bytes) -> str:
    return data.decode("gbk", errors="replace").replace("\x00", "")


def _lines(text: str) -> list[str]:
    return [ln.rstrip("\r") for ln in text.split("\n")]


def _field(fields: list[str], index: int) -> str:
    return fields[index] if index < len(fields) else ""


def _to_float(text: str) -> float:
    try:
        return float(text.strip())
    except (ValueError, AttributeError):
        return 0.0


def _to_int(text: str) -> int:
    try:
        return int(text.strip())
    except (ValueError, AttributeError):
        return 0


def unzip_zhb(data: bytes) -> dict[str, bytes]:
    """解压 zhb.zip 内容为 {文件名: 原始字节}。"""
    result: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            result[name] = zf.read(name)
    return result


def parse_tdxstat(data: bytes) -> list[TdxStat]:
    """解析 tdxstat.cfg → 个股综合统计指标。"""
    out: list[TdxStat] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 5 or f[1] == "":
            continue
        out.append(
            TdxStat(
                market=_to_int(f[0]),
                code=f[1],
                date=_field(f, 4),
                pe_ttm=_to_float(_field(f, 3)),
                trend_days=_to_int(_field(f, 5)),
                change_pct=_to_float(_field(f, 6)),
                pe_static=_to_float(_field(f, 9)),
                div_yield=_to_float(_field(f, 10)),
                chg_5=_to_float(_field(f, 28)),
                chg_10=_to_float(_field(f, 30)),
                chg_20=_to_float(_field(f, 18)),
                chg_60=_to_float(_field(f, 20)),
                chg_ytd=_to_float(_field(f, 21)),
                _fields=f,
            )
        )
    return out


def parse_tdxstat2(data: bytes) -> list[TdxStat2]:
    """解析 tdxstat2.cfg → 个股资金流向 + 板块归属。"""
    out: list[TdxStat2] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 14 or f[1] == "":
            continue
        out.append(
            TdxStat2(
                market=_to_int(f[0]),
                code=f[1],
                date=_field(f, 2),
                block_index=_field(f, 13),
                amount=_to_float(_field(f, 3)),
                amount_prev=_to_float(_field(f, 5)),
                ipo_price=_to_float(_field(f, 16)),
                high_52w=_to_float(_field(f, 17)),
                low_52w=_to_float(_field(f, 18)),
                _fields=f,
            )
        )
    return out


def parse_xgsg(data: bytes) -> list[TdxXgsg]:
    """解析 xgsg.cfg → 新股申购列表。"""
    out: list[TdxXgsg] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 15 or f[1] == "":
            continue
        out.append(
            TdxXgsg(
                market=_to_int(f[0]),
                code=f[1],
                date=_field(f, 2),
                issue_price=_to_float(_field(f, 3)),
                name=_field(f, 14),
                _fields=f,
            )
        )
    return out


def _is_sp_code(s: str) -> bool:
    return len(s) == 7 and s.isdigit()


def parse_spblock(data: bytes) -> list[SpBlock]:
    """解析 spblock.dat → 专业板块（大型指数成分）列表。"""
    out: list[SpBlock] = []
    cur: SpBlock | None = None
    for ln in _lines(_decode_gbk(data)):
        ln = ln.strip("\x00").strip()
        if ln == "":
            continue
        if ln.startswith("#"):
            cur = SpBlock(name=ln[1:].strip(), codes=[])
            out.append(cur)
            continue
        if cur is not None and _is_sp_code(ln):
            cur.codes.append(ln)
    return out


def spblock_by_name(blocks: list[SpBlock], name: str) -> SpBlock | None:
    for b in blocks:
        if b.name == name:
            return b
    return None


def parse_tdxzs(data: bytes) -> list[TdxZs]:
    """解析 tdxzs.cfg → 板块指数配置。"""
    out: list[TdxZs] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 2 or f[0] == "" or f[1] == "":
            continue
        out.append(
            TdxZs(
                name=f[0],
                code=f[1],
                type=_to_int(_field(f, 2)),
                sub_type=_to_int(_field(f, 3)),
                ref=_field(f, 5),
            )
        )
    return out


def parse_tdxbk(data: bytes) -> list[TdxBk]:
    """解析 tdxbk.cfg → 板块简称↔全称。"""
    out: list[TdxBk] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[1] == "" or f[2] == "":
            continue
        out.append(TdxBk(short=f[1], full=f[2]))
    return out


def parse_tdxhy(data: bytes) -> list[TdxHy]:
    """解析 tdxhy.cfg → 行业归属（每行 市场|代码|通达信行业|||申万行业）。"""
    out: list[TdxHy] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "":
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[0] == "":
            continue
        sw = f[5] if len(f) >= 6 else f[-1]
        out.append(
            TdxHy(
                market=_to_int(f[0][0]),
                code=f[1],
                tdx_hy=f[2],
                sw_hy=sw,
            )
        )
    return out


def fill_block_index_with_alias(blocks: list[SpBlock], zs: list[TdxZs], bk: list[TdxBk]) -> int:
    """用 tdxzs（名称→代码）+ tdxbk（简称→全称）为板块回填指数代码。

    返回命中数。未命中（``index`` 保持空串）说明该板块不在 tdxzs 中。
    """
    name_to_code = {z.name: z.code for z in zs}
    short_to_full = {b.short: b.full for b in bk}
    hit = 0
    for blk in blocks:
        code = name_to_code.get(blk.name)
        if code is None:
            code = name_to_code.get(short_to_full.get(blk.name, ""))
        if code:
            blk.index = code
            hit += 1
    return hit


def parse_tdx_ah_rate(data: bytes) -> list[TdxAhRate]:
    """解析 tdxahrate.cfg → A/H 股对照（``名称|A代码|H代码|flag``）。"""
    out: list[TdxAhRate] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[1] == "" or f[2] == "":
            continue
        out.append(TdxAhRate(name=f[0], a_code=f[1], h_code=f[2], flag=_to_int(_field(f, 3))))
    return out


def parse_tdx_adr(data: bytes) -> list[TdxAdr]:
    """解析 tdxadr.cfg → 港股/中概 ↔ ADR（``名称|代码|ADR|flag``）。"""
    out: list[TdxAdr] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[1] == "" or f[2] == "":
            continue
        out.append(TdxAdr(name=f[0], code=f[1], adr=f[2], flag=_to_int(_field(f, 3))))
    return out


def parse_tdx_chain(data: bytes) -> list[TdxChain]:
    """解析 tdxchain.cfg → 产业链板块（``板块代码|CYL代码|名称``）。"""
    out: list[TdxChain] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[0] == "":
            continue
        out.append(TdxChain(code=f[0], cyl_code=f[1], name=f[2]))
    return out


def parse_named_blocks(data: bytes) -> list[NamedBlock]:
    """解析 ``#板块名`` 形式的板块成分文件（jjblock/mgblock/hkblock/csiblock.dat）。

    成分行形如 ``市场,代码``（如 ``33,000176``）或纯代码（如美股 ``AAPL``）。
    代码保留原始文本（含逗号前缀时一并保留，便于还原市场）。
    """
    out: list[NamedBlock] = []
    current: NamedBlock | None = None
    for ln in _lines(_decode_gbk(data)):
        line = ln.strip()
        if line == "":
            continue
        if line.startswith("#"):
            current = NamedBlock(name=line[1:].strip(), codes=[])
            out.append(current)
        elif current is not None:
            current.codes.append(line)
    return out


def parse_brokers(data: bytes) -> list[TdxBroker]:
    """解析 brkcomp.dat → 券商/机构名录（``id|简称|全称``）。"""
    out: list[TdxBroker] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[0] == "":
            continue
        out.append(TdxBroker(id=_to_int(f[0]), short=f[1], full=f[2]))
    return out


def parse_simple_pairs(data: bytes, sep: str = _FIELD_SEP) -> list[tuple[str, str]]:
    """解析 ``代码<sep>名称`` 两列文件（tdxsbzs.cfg 等）。"""
    out: list[tuple[str, str]] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(sep)
        if len(f) < 2 or f[0] == "":
            continue
        out.append((f[0], f[1]))
    return out


def parse_ini(data: bytes) -> dict[str, dict[str, str]]:
    """解析 INI 风格配置（hqrule.dat / tend_std.cfg / neednote.dat）。"""
    sections: dict[str, dict[str, str]] = {}
    current = ""
    for ln in _lines(_decode_gbk(data)):
        line = ln.strip()
        if line == "" or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        key, sep, value = line.partition("=")
        if sep:
            sections.setdefault(current, {})[key.strip()] = value.strip()
    return sections


def parse_hk_zs_weight(data: bytes) -> list[tuple[str, float]]:
    """解析 hkzsinfo.cfg → 港股指数成分权重（``QZi=代码,权重``）。"""
    out: list[tuple[str, float]] = []
    for section in parse_ini(data).values():
        for key, value in section.items():
            if not key.upper().startswith("QZ"):
                continue
            parts = value.split(",")
            if len(parts) >= 2 and parts[0]:
                out.append((parts[0], _to_float(parts[1])))
    return out


def parse_csrc_industries(data: bytes) -> list[TdxIndustryNode]:
    """解析 incon.dat → 证监会行业分类（``代码|名称``，首行 #ZJHHY 为段标记）。"""
    out: list[TdxIndustryNode] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 2 or f[0] == "":
            continue
        code = f[0]
        level = 1 if len(code) <= 1 else (2 if len(code) <= 3 else 3)
        out.append(TdxIndustryNode(code=code, name=f[1], level=level))
    return out


def parse_index_names(data: bytes) -> list[TdxIndexName]:
    """解析 ilong.dat → 指数代码名称（``市场|代码||名称``）。"""
    out: list[TdxIndexName] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 4 or f[1] == "":
            continue
        out.append(TdxIndexName(market=_to_int(f[0]), code=f[1], name=f[3]))
    return out


def parse_stock_pinyin(data: bytes) -> list[TdxStockPinyin]:
    """解析 hspy.dat → 代码拼音缩写（``市场|代码|拼音``）。"""
    out: list[TdxStockPinyin] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 3 or f[1] == "":
            continue
        out.append(TdxStockPinyin(market=_to_int(f[0]), code=f[1], pinyin=f[2]))
    return out


def parse_code_name_table(data: bytes) -> list[TdxCodeName]:
    """解析 pttab.dat → 代码名称表（``市场,代码,名称``）。"""
    out: list[TdxCodeName] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(",")
        if len(f) < 3 or f[1] == "":
            continue
        out.append(TdxCodeName(market=_to_int(f[0]), code=f[1], name=f[2]))
    return out


def parse_bj_code_map(data: bytes) -> list[TdxBjCode]:
    """解析 addedcode_bj.cfg → 北交所新旧代码对照（``市场|旧码|新码|名称|日期``）。"""
    out: list[TdxBjCode] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#") or _FIELD_SEP not in ln:
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 4 or f[1] == "" or f[2] == "":
            continue
        out.append(
            TdxBjCode(
                market=_to_int(f[0]),
                old_code=f[1],
                new_code=f[2],
                name=f[3],
                date=_field(f, 4),
            )
        )
    return out


def parse_concept_map(data: bytes) -> list[TdxConcept]:
    """解析 tdxhkag.cfg / tdxmgag.cfg → 港股/美股 个股 ↔ 概念/行业映射。

    字段：``代码|名称|通达信行业|行业名||板块代码|板块名|扩展代码|``。
    """
    out: list[TdxConcept] = []
    for ln in _lines(_decode_gbk(data)):
        if ln == "" or ln.startswith("#"):
            continue
        f = ln.split(_FIELD_SEP)
        if len(f) < 7 or f[0] == "":
            continue
        out.append(
            TdxConcept(
                code=f[0],
                name=f[1],
                tdx_hy=_field(f, 2),
                hy_name=_field(f, 3),
                block_code=_field(f, 5),
                block_name=_field(f, 6),
                ext_code=_field(f, 7),
            )
        )
    return out


def parse_tdx_holidays(data: bytes) -> dict[int, list[str]]:
    """解析 needini.dat → {年份: [MMDD, ...]}（通达信内嵌节假日表）。"""
    out: dict[int, list[str]] = {}
    for ln in _lines(_decode_gbk(data)):
        line = ln.strip()
        if not line.startswith("Y"):
            continue
        _, _, value = line.partition("=")
        parts = [p for p in value.split(",") if p]
        if len(parts) < 2:
            continue
        year = _to_int(parts[0])
        if year <= 0:
            continue
        out[year] = parts[1:]
    return out
