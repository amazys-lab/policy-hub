# -*- coding: utf-8 -*-
"""地理结构 · 省内地级市全名单与**成品覆盖率标注**

为什么单独一份（2026-10-10 用户拍板）：
  省总表必须**诚实标注覆盖率** —— 只采了省内部份城市时，
  出「XX 省政策补贴总表」若不说清楚，客户会以为覆盖全省。
  覆盖率需要一份「全省共几个地级市」的底数：它既不是枚举中文名（enum_map），
  也不是记录字段（domains/**），故单列 `policy_hub/common/geo.json`。

**判据不重复**：城市码 → 省份 的唯一真值源仍是 `pipeline/enum_map.json` 的
`province` 表；本模块只做「该省全名单」与「已收录哪些」的**差集运算**，
不另造第二套省市映射（本项目已因判据分叉踩过多次）。
"""
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
# 省份 → 地级市全名单（仓内相对；T3 起不再硬编码盘符）
GEO_PATH = os.path.join(os.path.dirname(_HERE), "policy_hub", "common", "geo.json")
# 城市码 → 中文名 / 省份 的唯一真值源
ENUM_PATH = os.path.join(_HERE, "enum_map.json")

_CACHE = {}


def _geo():
    if "geo" not in _CACHE:
        with open(GEO_PATH, encoding="utf-8") as f:
            _CACHE["geo"] = json.load(f)
    return _CACHE["geo"]


def _enum():
    if "enum" not in _CACHE:
        with open(ENUM_PATH, encoding="utf-8") as f:
            _CACHE["enum"] = json.load(f)
    return _CACHE["enum"]


def all_cities(province):
    """该省全部地级市名（含省直辖县级市）；未登记省份返回 []。"""
    return list((_geo().get("provinces") or {}).get(province) or [])


def covered_codes(province):
    """已录入城市码（由 enum_map.province 派生）—— 加城自动跟随，无需手维护。"""
    prov_map = _enum().get("province") or {}
    return sorted(c for c, p in prov_map.items() if p == province)


def coverage(province, cities):
    """覆盖率标注数据。

    `cities` = **本表实际声明的范围**（城市码列表），而非库里全部已录城市 ——
    两者可能不同（例如只为珠三角 9 市出省表），标注必须反映本表真实范围。

    返回 {province, total, covered, covered_names, missing_names, complete}。
    省份未登记全名单时 total=None、missing_names=[]，调用方应跳过覆盖率行。
    """
    enum_city = _enum().get("city") or {}
    total_list = all_cities(province)
    codes = sorted({str(c).upper() for c in (cities or []) if c})
    names = [enum_city.get(c, c) for c in codes]
    if not total_list:
        return {"province": province, "total": None, "covered": codes,
                "covered_names": names, "missing_names": [], "complete": None}
    missing = [n for n in total_list if n not in set(names)]
    return {"province": province, "total": len(total_list), "covered": codes,
            "covered_names": names, "missing_names": missing,
            "complete": not missing}
