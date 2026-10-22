# -*- coding: utf-8 -*-
"""把「前端可采集字段契约」固化成 policy_hub/common/field_contract.json。
它回答一个问题：某城某身份，用户到底能填哪些字段？
  city_kind[CITY][kind] = 控件池(kind) ∩ 该城该身份白名单(kind)
  （白名单缺键 = 全字段渲染；白名单为空数组 = 整份表单空白，等价于"什么都填不了"）
  city_kind[CITY]['hukou'] = 通用 hkBox 字段 ∪ 该城 HK_EXTRA 附加字段
  kind_global['overseas'] = collectOs() 的固定字段集
gate_validate.py 的第 11 项校验消费本文件：cond 引用的字段必须落在这里面。
用法：node extract_frontend.js && python export_field_contract.py
"""
import json, os, re, sys, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# 源库根 = pipeline/ 的上一级（仓内相对，不再硬编码盘符 · T3 2026-10-09）
SRC_ROOT = os.path.dirname(HERE)
CLIENT = os.path.join(SRC_ROOT, "server/static/client.html")
OUT = os.path.join(SRC_ROOT, "policy_hub/common/field_contract.json")

FE = json.load(open(os.path.join(HERE, "_frontend.json"), encoding="utf-8"))
fbk = FE["formByKind"]
static = FE["staticFields"]
cityFields = FE["cityFields"]
hkExtra = FE.get("hkExtra") or {}

KINDS = ("person", "entrepreneur", "unit")

# collectHk() 实际取值字段（含派生 housing_own_months / ss_months）
HK_BASE = {
    "age", "gender", "education_level", "is_full_time", "grad_years", "never_received",
    "title_level", "skill_level", "ss_years", "in_shortage_catalog", "has_skill_award",
    "healthy", "no_crime", "has_sz_social_insurance", "has_residence_permit", "still_paying_ss",
    "housing_own_years", "housing_rent_years", "housing_own_months", "housing_rent_months",
    "pension_or_medical_years", "ss_months", "ss_kinds_count", "has_overseas_qualification",
    "overseas_degree", "visiting_scholar_1y", "tax_legal_3y", "tax_shareholder_3y",
    "tax_iit_3y", "tax_individual_3y", "same_enterprise_3y", "family_relation",
    "has_sz_family_huji", "spouse_separate_years", "sz_huji_years",
    "has_special_policy_case", "special_kind", "identities",
}


def control_pool(kind):
    s = set()
    if kind in ("person", "entrepreneur"):
        cfg = fbk.get(kind) or {}
        for k in ("nums", "bools", "radio"):
            s |= set(cfg.get(k) or [])
        if cfg.get("tagField"):
            s.add(cfg["tagField"])
        if cfg.get("tagField2"):
            s.add(cfg["tagField2"])
    if kind in ("person", "unit"):
        s |= set(static.get("hsBox") or [])
    if kind == "unit":
        s |= set(static.get("entBox") or [])
    return s


def hk_pool(city):
    ex = hkExtra.get(city) or {}
    s = set(HK_BASE)
    for k in ("bools", "nums", "texts"):
        s |= set((ex.get(k) or {}).keys())
    if ex.get("identities"):
        s.add("identities")
    return s


def os_pool():
    """collectOs() 的固定字段集：直接从源码里扫 os_* 标识符 + identities。"""
    try:
        t = open(CLIENT, encoding="utf-8").read()
    except Exception:
        return []
    i = t.find("function collectOs()")
    if i < 0:
        return []
    j = t.find("\n}", i)
    seg = t[i:j if j > 0 else i + 4000]
    return sorted(set(re.findall(r"\bos_[a-z0-9_]+", seg)) | {"identities"})


def main():
    POOL = {k: control_pool(k) for k in KINDS}
    city_kind = {}
    notes = {}
    for city, info in cityFields.items():
        fields = (info.get("fields") or {})
        entry = {}
        for k in KINDS:
            if k not in fields:
                # 白名单缺键 → 全字段渲染 → 可填 = 整个控件池
                entry[k] = sorted(POOL[k])
                notes.setdefault(city, {})[k] = "kind-missing(全渲染)"
            elif not fields[k]:
                entry[k] = []
                notes.setdefault(city, {})[k] = "empty(整份表单空白)"
            else:
                entry[k] = sorted(set(POOL[k]) & set(fields[k]))
        entry["hukou"] = sorted(hk_pool(city))
        city_kind[city] = entry

    payload = {
        "_meta": {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "server/static/client.html",
            "generator": "pipeline/export_field_contract.py",
            "note": "某城某身份用户实际可填字段 = 控件池 ∩ 白名单。gate_validate 第 11 项据此判定 cond 引用字段是否可达。",
            "kind_flags": notes,
        },
        "city_kind": city_kind,
        "pool_by_kind": {k: sorted(POOL[k]) for k in KINDS},
        "hk_base": sorted(HK_BASE),
        "kind_global": {"overseas": os_pool()},
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("wrote", OUT)
    print("城市数:", len(city_kind))
    for k in KINDS:
        print("  %-12s 控件池 %d" % (k, len(POOL[k])))
    print("  hukou(SZ)   ", len(city_kind.get("SZ", {}).get("hukou", [])))
    print("  overseas    ", len(payload["kind_global"]["overseas"]))
    if notes:
        print("  白名单异常:", json.dumps(notes, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
