# -*- coding: utf-8 -*-
"""
聚合层：统一画像一次输入 -> 分别调用各域 -> 去状态分组 -> 统一输出。
- 只有一套引擎(engine/matcher.py)，各域只提供数据/规则；
- framework(落户待采) / deferred(留学生暂缓) 空域正常返回，绝不报错；
- 跨域去重/叠加互斥规则统一在本层处理(本版先按域分组，叠加规则待数据到位再补)。
运行：python -m policy_hub.aggregator.aggregate   (库为空时只做容器自检，有数据时顺带验证命中与金额)
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import matcher  # noqa: E402

DOM = ROOT / "domains"

def _load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

def _city_bundle(profile, rel):
    """多城市装载：只读 profile.city 指定的城市目录，不设默认城、不跨城猜测。

    未指定城市、或该城没有这个域的文件 ⇒ 返回 None，交各域容错分支（status=missing）。
    这是有意的：数据由使用者自己采集，引擎不替任何人假设「默认是哪座城」。
    """
    city = (profile or {}).get("city")
    if not city:
        return None
    return _load(DOM / "cities" / str(city).lower() / rel)

def run_domain_employment(profile):
    bundle = _city_bundle(profile, "employment_startup/programs.json")
    if not bundle:
        return {"status": "missing", "match": [], "near": [], "no": []}
    match, near, exited = [], [], []
    for pol in bundle["programs"]:
        r = matcher.classify(profile, pol)
        if r["status"] == "match":
            (exited if r["valid"] == "exited" else match).append(r)
        elif r["status"] == "near":
            near.append(r)
    return {"status": "active", "match": match, "near": near,
            "exited_or_renamed": exited, "count": len(bundle["programs"])}

def run_domain_hukou(profile):
    b = _city_bundle(profile, "hukou/channels.json")
    if not b:
        return {"status": "missing", "decisions": [], "to_collect": []}
    decisions, todo = [], []
    for c in b["channels"]:
        if c.get("cond"):
            d = matcher.channel_decide(profile, c)
            d["guide_url"] = c.get("guide_url")
            decisions.append(d)
        else:
            todo.append({"id": c["id"], "name": c["name"], "collect_fields": c["collect_fields"]})
    return {"status": b["status"], "decisions": decisions, "to_collect": todo, "note": b.get("note", "")}

def run_domain_overseas(profile):
    b = _city_bundle(profile, "overseas/programs.json") or {}
    if b.get("status") == "deferred" or not b.get("programs"):
        return {"status": b.get("status", "deferred"), "match": [], "near": [], "items": b.get("programs", [])}
    match, near = [], []
    for pol in b["programs"]:
        r = matcher.classify(profile, pol)
        if r["status"] == "match":
            match.append(r)
        elif r["status"] == "near":
            near.append(r)
    return {"status": b["status"], "match": match, "near": near, "count": len(b["programs"])}

def run_domain_enterprise(profile):
    bundle = _city_bundle(profile, "enterprise_support/programs.json")
    if not bundle:
        return {"status": "missing", "match": [], "near": []}
    match, near = [], []
    for pol in bundle["programs"]:
        r = matcher.classify(profile, pol)
        if r["status"] == "match":
            match.append(r)
        elif r["status"] == "near":
            near.append(r)
    return {"status": bundle.get("status", "active"), "match": match, "near": near,
            "count": len(bundle["programs"])}

def _run_simple(folder, profile):
    bundle = _city_bundle(profile, folder + "/programs.json")
    if not bundle:
        return {"status": "missing", "match": [], "near": []}
    match, near = [], []
    for pol in bundle["programs"]:
        r = matcher.classify(profile, pol)
        if r["status"] == "match": match.append(r)
        elif r["status"] == "near": near.append(r)
    return {"status": bundle.get("status", "active"), "match": match, "near": near,
            "count": len(bundle["programs"])}

def run_domain_housing(profile): return _run_simple("housing", profile)
def run_domain_tech(profile): return _run_simple("tech_enterprise", profile)
def run_domain_gba(profile): return _run_simple("gba_tax", profile)
def run_domain_inclusive(profile): return _run_simple("inclusive_tax", profile)
def run_domain_vocational(profile): return _run_simple("vocational_training", profile)

def aggregate(profile):
    emp, hk, ov = run_domain_employment(profile), run_domain_hukou(profile), run_domain_overseas(profile)
    ent = run_domain_enterprise(profile)
    hs, tc = run_domain_housing(profile), run_domain_tech(profile)
    gba = run_domain_gba(profile)
    inc = run_domain_inclusive(profile)
    vt = run_domain_vocational(profile)
    return {
        "profile": profile,
        "domains": {"employment_startup": emp, "hukou": hk, "overseas": ov,
                    "enterprise_support": ent, "housing": hs, "tech_enterprise": tc,
                    "gba_tax": gba, "inclusive_tax": inc, "vocational_training": vt},
        "summary": {
            "employment_match": [x["id"] for x in emp["match"]],
            "employment_near": len(emp["near"]),
            "hukou_eligible": [d["id"] for d in hk["decisions"] if d["status"] == "eligible"],
            "hukou_near": [d["id"] for d in hk["decisions"] if d["status"] == "near"],
            "hukou_to_collect": [c["id"] for c in hk["to_collect"]],
            "overseas_status": ov["status"],
            "overseas_match": [x["id"] for x in ov.get("match", [])],
            "enterprise_match": [x["id"] for x in ent.get("match", [])],
            "housing_match": [x["id"] for x in hs.get("match", [])],
            "tech_match": [x["id"] for x in tc.get("match", [])],
            "gba_match": [x["id"] for x in gba.get("match", [])],
            "inclusive_match": [x["id"] for x in inc.get("match", [])],
            "vocational_match": [x["id"] for x in vt.get("match", [])],
        },
    }

# ---------- 自检 ----------
# 本仓不附带政策数据，所以这段自检不绑定任何具体政策 ID、城市或金额：
#   库为空（默认状态）⇒ 只验证「九域容器齐备 + 缺数据不报错」，并提示怎么接入数据；
#   库里有数据      ⇒ 额外验证「命中项的城市码已在 schema 登记」与「金额可累加」。
def _library_stats():
    """数一遍 domains/cities 下的条目，供自检提示用。"""
    files = programs = channels = 0
    cities = DOM / "cities"
    if not cities.exists():
        return 0, 0, 0
    for p in sorted(cities.rglob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        files += 1
        programs += len(d.get("programs") or [])
        channels += len(d.get("channels") or [])
    return files, programs, channels


if __name__ == "__main__":
    files, programs, channels = _library_stats()
    print("库中数据：%d 个文件 / %d 条政策 / %d 条通道" % (files, programs, channels))

    if not programs and not channels:
        print("\n当前没有任何政策数据 —— 这是本仓的默认状态，数据不随仓分发。")
        print("接入方式见 policy_hub/domains/README.md，四步：")
        print("  1) python pipeline/register_city_codes.py     # 登记城市码（已内置 51 个，可跳过）")
        print("  2) cp policy_hub/templates/new_city/programs.template.json \\")
        print("        policy_hub/domains/cities/<城市码小写>/<域英文名>/programs.json")
        print("  3) 逐条填写（官方文号 + *.gov.cn 原文链接，达不到 L4 就标 to_collect）")
        print("  4) python pipeline/check_data.py             # 字段契约 + 枚举 + ID 唯一性")
        r = aggregate({"kind": "person", "city": ""})
        for k, d in r["domains"].items():
            assert isinstance(d, dict) and ("match" in d or "decisions" in d), (k, list(d))
        assert r["summary"]["employment_match"] == [], r["summary"]["employment_match"]
        print("\n空库自检通过：九域容器齐备，缺数据不报错。")
        raise SystemExit(0)

    # 取第一个有数据的城市作为自检样本（不假设具体是哪座城）
    sample = None
    for p in sorted((DOM / "cities").iterdir()):
        if p.is_dir() and any(p.rglob("*.json")):
            sample = p.name.upper()
            break
    print("自检样本城市：%s" % (sample or "(根级旧布局)"))

    r = aggregate({"kind": "unit", "city": sample})
    fresh = {"is_full_time": True, "education_level": 4, "grad_years": 1,
             "never_received": True, "healthy": True, "no_crime": True, "city": sample}
    rh = aggregate(fresh)
    print("示例(应届本科)：可走落户通道", rh["summary"]["hukou_eligible"],
          "| 待采", rh["summary"]["hukou_to_collect"], "| 留学生", rh["summary"]["overseas_status"])

    # ① 命中项的 ID 前缀必须是已登记的城市码（防止串城或手写错码）
    schema = json.loads((ROOT / "common" / "schema.json").read_text(encoding="utf-8"))
    codes = set(schema.get("city_code") or {})
    smb = {"kind": "unit", "city": sample, "ent_scale": "smb", "ui_paid_months": 24,
           "not_zombie": True, "no_layoff": True, "ui_premium_lastyear": 100000}
    hit = aggregate(smb)["domains"]["enterprise_support"]["match"]
    bad = [x["id"] for x in hit if str(x["id"]).split("-")[0] not in codes]
    assert not bad, bad

    # ② 金额测算：命中项的 amount 可累加
    total = sum(float(x.get("amount") or 0) for x in hit)
    print("企业用工域：命中 %d 条，金额合计 ¥%s" % (len(hit), format(total, ",.0f")))

    # ③ 九个域的返回结构完整（容器不塌：match/near 或 decisions/to_collect）
    for k, d in r["domains"].items():
        assert isinstance(d, dict), (k, type(d))
        assert ("match" in d or "decisions" in d), (k, list(d))
    print("九域返回结构完整：match / near / decisions / to_collect 容器齐备")

