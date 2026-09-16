"""zhb.zip 新增配置文件解析测试（离线）。"""

from __future__ import annotations

import pytest

from easy_tdx import TdxClient
from easy_tdx.codec.configdata import (
    parse_bj_code_map,
    parse_brokers,
    parse_code_name_table,
    parse_concept_map,
    parse_csrc_industries,
    parse_hk_zs_weight,
    parse_index_names,
    parse_ini,
    parse_named_blocks,
    parse_positional,
    parse_simple_pairs,
    parse_stock_pinyin,
    parse_tdx_adr,
    parse_tdx_ah_rate,
    parse_tdx_chain,
    parse_tdx_holidays,
)


def _gbk(text: str) -> bytes:
    return text.encode("gbk")


def test_parse_ah_rate() -> None:
    data = _gbk("比亚迪|002594|01211|1\r\n中国平安|601318|02318|1\r\n")
    out = parse_tdx_ah_rate(data)
    assert len(out) == 2
    assert (out[0].name, out[0].a_code, out[0].h_code, out[0].flag) == (
        "比亚迪",
        "002594",
        "01211",
        1,
    )
    assert out[1].h_code == "02318"


def test_parse_adr() -> None:
    data = _gbk("阿里巴巴-SW|09988|BABA|8\r\n百度集团-SW|09888|BIDU|8\r\n")
    out = parse_tdx_adr(data)
    assert [(x.code, x.adr) for x in out] == [("09988", "BABA"), ("09888", "BIDU")]


def test_parse_chain() -> None:
    data = _gbk("880506|CYL00210|新基建-5G\r\n880507|CYL00162|军工\r\n")
    out = parse_tdx_chain(data)
    assert out[0].code == "880506" and out[0].cyl_code == "CYL00210" and out[0].name == "新基建-5G"


def test_parse_named_blocks() -> None:
    data = _gbk("#恒指成份股\r\n00001\r\n00002\r\n#道琼斯成份股\r\nAAPL\r\nAMGN\r\n")
    out = parse_named_blocks(data)
    assert [b.name for b in out] == ["恒指成份股", "道琼斯成份股"]
    assert out[0].codes == ["00001", "00002"]
    assert out[1].codes == ["AAPL", "AMGN"]
    # 市场,代码 形式
    assert parse_named_blocks(_gbk("#基金\r\n33,000176\r\n"))[0].codes == ["33,000176"]


def test_parse_holidays() -> None:
    data = _gbk("[Holiday]\r\nNUM=2\r\nY2024=2024,0101,0210,0211,0212,\r\nY2025=2025,0101,\r\n")
    out = parse_tdx_holidays(data)
    assert out[2024] == ["0101", "0210", "0211", "0212"]
    assert out[2025] == ["0101"]


def test_parse_extra_text_files() -> None:
    assert parse_brokers(_gbk("1|巴克莱|巴克莱亚洲有限公司\r\n"))[0].full == "巴克莱亚洲有限公司"
    assert parse_simple_pairs(_gbk("899001|三板成指成份股\r\n"))[0] == ("899001", "三板成指成份股")
    assert parse_hk_zs_weight(_gbk("[HSI_QZ]\r\nQZ1=00001,1.10\r\n"))[0] == ("00001", 1.10)
    nodes = parse_csrc_industries(_gbk("#ZJHHY\r\nA|农、林、牧、渔业\r\nA01|农业\r\n"))
    assert (nodes[0].code, nodes[0].level) == ("A", 1)
    assert (nodes[1].code, nodes[1].level) == ("A01", 2)
    assert (
        parse_index_names(_gbk("62|CES100||中华港股通精选100\r\n"))[0].name == "中华港股通精选100"
    )
    assert parse_stock_pinyin(_gbk("0|002839|ZJGH\r\n"))[0].pinyin == "ZJGH"
    assert parse_code_name_table(_gbk("0,000003,深金田A\r\n"))[0].name == "深金田A"


def test_parse_bj_and_concept() -> None:
    bj = parse_bj_code_map(
        _gbk("000000,0,346,20260916,\r\n44|832000|920000|安徽凤凰(已切换)|20251009\r\n")
    )
    assert len(bj) == 1 and bj[0].old_code == "832000" and bj[0].new_code == "920000"
    con = parse_concept_map(_gbk("AAPL|苹果电脑||苹果概念||880574|美股-苹果概念|US0219|\r\n"))
    assert con[0].block_name == "美股-苹果概念" and con[0].ext_code == "US0219"


def test_parse_ini() -> None:
    ini = parse_ini(
        _gbk("[Data]\r\nRecentCFETSHoliday=20260101,20260102,\r\nHSXS3Breed=706080\r\n")
    )
    assert ini["Data"]["HSXS3Breed"] == "706080"
    assert ini["Data"]["RecentCFETSHoliday"].startswith("20260101")


def test_parse_positional() -> None:
    rows = parse_positional(_gbk("#comment\r\n0|300727|123285|37000.0|润禾转02\r\n"))
    assert rows == [["0", "300727", "123285", "37000.0", "润禾转02"]]
    assert parse_positional(_gbk("\r\n")) == []


def test_client_zhb_positional(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1")
    monkeypatch.setattr(
        c, "_zhb_member", lambda name: _gbk("0|300727|润禾转02\r\n0|301628|强达转债\r\n")
    )
    df = c.get_zhb_positional("othersg.cfg")
    assert list(df.columns) == ["c0", "c1", "c2"]
    assert df.iloc[1]["c2"] == "强达转债"


def test_client_zhb_getters(monkeypatch: pytest.MonkeyPatch) -> None:
    c = TdxClient(host="127.0.0.1")
    members = {
        "tdxahrate.cfg": _gbk("比亚迪|002594|01211|1\r\n"),
        "tdxadr.cfg": _gbk("阿里巴巴-SW|09988|BABA|8\r\n"),
        "tdxchain.cfg": _gbk("880506|CYL00210|新基建-5G\r\n"),
        "hkblock.dat": _gbk("#恒指成份股\r\n00001\r\n"),
        "needini.dat": _gbk("[Holiday]\r\nY2024=2024,0101,\r\n"),
    }
    monkeypatch.setattr(c, "_zhb_member", lambda name: members.get(name, b""))

    assert len(c.get_ah_rates()) == 1
    assert c.get_adr_list().iloc[0]["adr"] == "BABA"
    assert c.get_industry_chain().iloc[0]["cyl_code"] == "CYL00210"
    blocks = c.get_named_blocks("hkblock.dat")
    assert list(blocks.columns) == ["block", "code"] and blocks.iloc[0]["code"] == "00001"
    holidays = c.get_tdx_holidays()
    assert holidays.iloc[0]["date"] == "2024-01-01"
