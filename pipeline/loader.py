# -*- coding: utf-8 -*-
"""
政策库读取器 · 源目录只读
--------------------------------------------------
数据布局有两个入口，必须同时读，否则会漏掉旧版单城文件：
  1) policy_hub/domains/<域>/programs.json        ← 旧版 2 层布局（无城目录层，本仓已不再使用）
  2) policy_hub/domains/cities/<城>/<域>/*.json   ← 当前布局（本仓默认为空，数据由使用者填入）

★ 不在这里写「几条记录 / 几座城市」：那些数随采集增长，写死必腐。
  真值源 = `python pipeline/check_data.py` 现算。
"""
import json
import os
import glob

# 源库根 = 本文件（pipeline/）的上一级 —— 仓内相对，不再硬编码盘符（T3 · 2026-10-09）
DEFAULT_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 记录里字段值与所在目录不一致的情况：(id, 字段, 记录值, 目录值, 来源)
# 导出时以目录为准，但把不一致全部报出来给人工复核
MISMATCH = []

# 长三角 / 珠三角等预设包。
# ★ 只有「固定地理口径」才在这里写死成员（珠三角 9 市、长三角 4 市、广西南宁+钦州
#   = 已采集合本身）；`all` 走 None = 全库。数量随采集增长的注释一律不写（会腐）。
PRESETS = {
    "gd": ["SZ", "GZ", "DG", "FS", "ZS", "ZH", "JM", "ZQ", "HZ"],       # 广东·珠三角 9 市
    "yrd": ["SU", "NJ", "HG", "NB"],                                    # 长三角（已采集城市）
    "gx": ["NN", "QZ"],                                                 # 广西（南宁、钦州）
    "all": None,                                                        # 全部城市
}


# 旧版 2 层布局的路径里没有城市码 ⇒ 只能约定一个。本仓无该目录；
# 若要兼容你自己的旧库，把它改成本库顶层文件对应的城市码。
LEGACY_TOP_CITY = "SZ"


def load_all(src=DEFAULT_SRC):
    """返回 [{city, domain, sub_domain, name, ...}, ...]，源文件全程只读。"""
    rows = []

    # 1) 旧版 2 层布局：domains/<域>/programs.json（无城目录 ⇒ 城市码只能约定）
    for fp in sorted(glob.glob(os.path.join(src, "policy_hub", "domains", "*", "programs.json"))
                     + glob.glob(os.path.join(src, "policy_hub", "domains", "*", "channels.json"))):
        dom = os.path.basename(os.path.dirname(fp))
        rows += _read(fp, LEGACY_TOP_CITY, dom)

    # 2) 其余城市：domains/cities/<城>/<域>/（3 层）
    for fp in sorted(glob.glob(os.path.join(src, "policy_hub", "domains", "cities", "*", "*", "programs.json"))
                     + glob.glob(os.path.join(src, "policy_hub", "domains", "cities", "*", "*", "channels.json"))):
        parts = os.path.normpath(fp).split(os.sep)
        city, dom = parts[-3].upper(), parts[-2]
        rows += _read(fp, city, dom)

    return rows


def _read(fp, city, dom):
    try:
        with open(fp, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        print(f"  [WARN] 读取失败 {fp}: {e}")
        return []
    items = d.get("programs") or d.get("channels") or []
    if not isinstance(items, list):
        items = [items]
    out = []
    for it in items:
        if isinstance(it, dict):
            # city：以记录自身字段为准（overseas 域跨城混放在同一文件里）
            it["city"] = str(it.get("city") or city).upper()
            # domain：以目录为准（目录不会错；曾出现记录把 domain 写成城市码）
            raw_dom = it.get("domain")
            if raw_dom and str(raw_dom) != dom:
                MISMATCH.append((it.get("id"), "domain", raw_dom, dom,
                                 os.path.relpath(fp, DEFAULT_SRC)))
            it["domain"] = dom
            it["_domain_raw"] = raw_dom
            it["_src"] = os.path.relpath(fp, DEFAULT_SRC)
            out.append(it)
    return out


def filter_cities(rows, cities):
    if not cities:
        return rows
    cs = {c.upper() for c in cities}
    return [r for r in rows if str(r.get("city", "")).upper() in cs]


VALID_ACTIVE = "active"


def filter_active(rows):
    """成品层收录口径：**只接入现行有效政策**（2026-10-10 用户拍板）。

    非现役（`exited` / `renamed` / `merged` / `superseded`）**仍留在库里**，
    前端也仍以「已退出实施·备查」区块展示 —— 但**不进售卖成品**：
    成品是「你能申报的政策」清单，把已下线政策卖给客户只会让他白跑一趟
    （前端是知识库、成品是可用清单，两者定位不同，见 contract.md §10.2）。

    判据真值源 = 唯一的 `valid == "active"`，**不在这里另列表** ——
    否则与 `gate_validate.VALID_VALID` / 前端分支形成"两套词典分叉"
    （本项目已因判据分叉踩过多次）。缺 `valid` 键时按引擎同款兜底视为 active
    （闸门第 19 项已把"缺 valid"拦在入库前）。
    """
    return [r for r in rows if str(r.get("valid") or VALID_ACTIVE).strip() == VALID_ACTIVE]


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    rs = load_all()
    print("总条目:", len(rs))
    import collections
    print("按城市:", dict(collections.Counter(r["city"] for r in rs)))
    for k, v in PRESETS.items():
        n = len(filter_cities(rs, v)) if v else len(rs)
        print(f"  预设 {k:5} -> {n} 条")
