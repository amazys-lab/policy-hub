# -*- coding: utf-8 -*-
"""
统一匹配引擎（全域唯一一套，规则与数据分离）。
- 就业创业域：result_type=money（条件匹配 + 金额测算）
- 落户域：    result_type=channel（通道决策树，输出可走通道/差什么）
- 留学生域：  result_type=review（叠加+评审，只做资格预判，不承诺结果）
规则结构沿用已验证的 cond={applicant_kinds,any_identities,must:[{f,op,v,label}]}。
"""

def _default_for(v):
    if isinstance(v, bool): return False
    if isinstance(v, list): return []
    return 0

def cond_ok(profile, c):
    f, op, v = c["f"], c["op"], c["v"]
    a = profile.get(f, _default_for(v))
    try:
        if op == ">=": return a >= v
        if op == "<=": return a <= v
        if op == ">": return a > v
        if op == "<": return a < v
        if op == "==": return a == v
        if op == "!=": return a != v
        if op == "intersects": return len(set(a or []) & set(v)) > 0
    except TypeError:
        return False
    return False

# 画像 kind → 其可命中的主体集合。`overseas` 是**叠加身份**：留学/海外人才首先是个"人"，
# 所以选「海外人才」画像时，标 `person` 的政策同样应命中（D2 · 2026-10-10 用户拍板）。
# 反向**不成立**：选「个人」画像不吃 only-overseas 的政策（国内个人 ≠ 海外人才）。
PROFILE_KIND_EXPAND = {"overseas": ("overseas", "person")}


def effective_kinds(kind):
    """画像 kind → 其可命中的主体集合（含叠加展开）。统一返回元组，调用方按集合求交。"""
    return PROFILE_KIND_EXPAND.get(kind, (kind,))


def evaluate(profile, pol):
    """返回 skip / no / near / match / exited-near / exited-match 由调用方结合 valid 处理。"""
    kinds = pol["cond"]["applicant_kinds"]
    if not (set(effective_kinds(profile.get("kind"))) & set(kinds)):
        return "skip"
    tags = pol["cond"].get("any_identities", [])
    if tags and not (set(profile.get("identities", [])) & set(tags)):
        return "no"
    must = pol["cond"]["must"]
    fails = [c["label"] for c in must if not cond_ok(profile, c)]
    am = pol["cond"].get("any_must")  # {label, conds:[...]} 组内满足其一即可
    total = len(must) + (1 if am else 0)
    if am and not any(cond_ok(profile, c) for c in am.get("conds", [])):
        fails.append(am["label"])
    if not fails:
        return "match"
    return "near" if len(fails) < total else "no"

def estimate(profile, am):
    """金额测算（money 型）。无法测算返回 None。"""
    if not am: return None
    k = am.get("kind")
    if k == "once": return am["value"]
    if k in ("once_x_count", "month_x_count"):
        return am["per"] * int(profile.get(am["count_field"], 0) or 0)
    if k == "tiered_hire":
        n = int(profile.get(am["count_field"], 0) or 0)
        first = min(n, am["first_n"]); rest = max(0, n - am["first_n"])
        return min(am["cap"], first * am["first"] + rest * am["rest"])
    if k == "per_year_x_count":  # 每人每年定额 × 人数（税收定额扣减，按年，最长年限在政策文本说明）
        return am["per"] * int(profile.get(am["count_field"], 0) or 0)
    if k == "percent_of_base":   # 按某基数(如上年实缴失业险)×比例返还
        base = float(profile.get(am["base_field"], 0) or 0)
        return round(base * am["ratio"], 2)
    return None

def classify(profile, pol):
    """统一分类：附带 valid 状态与未满足项，供聚合层使用。"""
    st = evaluate(profile, pol)
    out = {"id": pol["id"], "domain": pol.get("domain"), "name": pol["name"],
           "result_type": pol.get("result_type", "money"),
           "valid": pol.get("valid", "active"), "status": st, "missing": []}
    if st in ("near", "no"):
        out["missing"] = [c["label"] for c in pol["cond"]["must"] if not cond_ok(profile, c)]
        _am = pol["cond"].get("any_must")
        if _am and not any(cond_ok(profile, c) for c in _am.get("conds", [])):
            out["missing"].append(_am["label"])
    if st == "match":
        out["amount"] = estimate(profile, pol.get("amount"))
    return out


# ---------- 落户通道决策（channel 型）：基本条件全满足 AND 分支任一满足 ----------
def _fails(profile, must):
    return [c["label"] for c in (must or []) if not cond_ok(profile, c)]

def estimate_points(profile, sr):
    """积分入户预估分（规则估算，非承诺）。无 score_rule 返回 None。"""
    if not sr:
        return None
    own_m = int(profile.get(sr["own_field"], 0) or 0)
    rent_m = int(profile.get(sr["rent_field"], 0) or 0)
    # 自有住房与合法租赁同时段不累加、取高；简化模型按各自总分取高
    housing = max(own_m * sr["own_per_month"], rent_m * sr["rent_per_month"])
    ss_m = int(profile.get(sr["ss_months_field"], 0) or 0)
    ss_kinds = int(profile.get(sr["ss_kinds_field"], 0) or 0)
    ss = ss_m * sr["ss_per_kind_month"] * ss_kinds
    bonus = int(profile.get(sr.get("bonus_field", "_none"), 0) or 0)
    return round(housing + ss + bonus, 1)

def channel_decide(profile, ch):
    """对一条落户通道做决策。ch["cond"] = {base_must, branches(可选), score_rule(可选)}。
    返回 eligible / near / no；near 表示基本条件满足但差分支或材料，no 表示硬门槛不满足。"""
    cond = ch.get("cond")
    out = {"id": ch["id"], "name": ch["name"], "channel_type": ch.get("channel_type"),
           "approval_type": "competition" if ch.get("channel_type") == "competition" else "approval",
           "status": "no", "missing": [], "branch_hit": None, "score": None}
    if not cond:  # 待采集通道不判定
        out["status"] = "to_collect"
        return out
    base_miss = _fails(profile, cond.get("base_must"))
    if base_miss:
        out["missing"] = base_miss
        out["status"] = "no"
        return out
    branches = cond.get("branches")
    if branches:
        for i, br in enumerate(branches):
            miss = _fails(profile, br.get("must"))
            if not miss:
                out["branch_hit"] = br.get("name", f"分支{i+1}")
                break
        if out["branch_hit"] is None:
            # 基本条件满足、但无任一分支达标：给出最接近分支所差项
            best = min((_fails(profile, br.get("must")) for br in branches), key=len)
            out["missing"] = best
            out["status"] = "near"
            return out
    if "score_rule" in cond and cond["score_rule"]:
        out["score"] = estimate_points(profile, cond["score_rule"])
    out["status"] = "eligible"
    return out
