"""演示：配置类加工数据（zhb.zip）。

通过标准协议 0x06B9 下载 zhb.zip（46 个配置文件），解析出：
  - tdxstat / tdxstat2   个股统计 / 资金流向 + 板块归属
  - xgsg                 新股申购
  - spblock              大型指数成分（中证2000/1000/500 等）
  - tdxzs / tdxbk        板块指数代码 / 简称↔全称
  - tdxhy                行业归属（通达信 + 申万）

使用客户端：TdxClient（同步）
"""

from easy_tdx import TdxClient

with TdxClient.from_best_host() as c:
    # 1. 个股综合统计（PE/股息率/连涨跌/区间涨幅）
    stat = c.get_tdx_stat()
    print("个股统计:", stat.shape)
    print(stat[stat["code"] == "600519"].to_string(index=False))

    # 2. 资金流向 + 板块归属
    stat2 = c.get_tdx_stat2()
    print("\n资金流+板块:", stat2[stat2["code"] == "600519"].to_string(index=False))

    # 3. 新股申购
    xgsg = c.get_xgsg()
    print("\n新股申购:", xgsg.shape)
    print(xgsg.head(3).to_string(index=False))

    # 4. 大型指数成分
    sp = c.get_spblock()
    for name in ("中证2000", "中证500", "国证2000"):
        blk = next((b for b in sp if b.name == name), None)
        print(
            f"{name}: 成分 {len(blk.codes) if blk else 0} 只, 指数代码={blk.index if blk else '-'}"
        )

    # 5. 行业归属
    hy = c.get_tdx_hy()
    print("\n行业归属:", hy[hy["code"] == "600519"].to_string(index=False))
