# -*- coding: utf-8 -*-
"""
阶段A · 政策智能匹配只读 API（FastAPI）
------------------------------------------------------------------
运行（项目根目录）：
    python -m uvicorn server.app:app --reload --port 8000
然后浏览器打开：
    http://127.0.0.1:8000/docs         交互式接口文档(可直接点 Try 调试)
    http://127.0.0.1:8000/api/v1/meta  元信息

设计：
- 匹配引擎直接复用 policy_hub（已被画像回归验证），线上不重写规则；
- **单一数据源**：所有接口（match / meta / policies / topic）都读源库 policy_hub/domains/，
  与 server/publish_db.py 共用同一套装载与字段注入（record_norm.inject），
  所以「清单看到的」和「匹配出来的」永远是同一个版本；
- policy.db 退回「发布记录 + 数据确权快照」的角色，只提供 data_version（不再提供条目内容）；
- match 结果带 data_version 与 source_version（发布区数据字节指纹），可追溯；
- 金额/积分均为规则估算，出参统一带免责声明，review/competition 不承诺结果。
"""
import os, sys, sqlite3, json, datetime
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "policy_hub"))
from aggregator.aggregate import aggregate  # noqa: E402

# ★ 域中文标签的**唯一真值源** = `pipeline/enum_map.json::domain`（经 `mappers.t("domain", x)`）。
#   2026-10-17（C 项）：此前本文件另写了一份 `labels` 字典，与 enum_map / export_pdf /
#   build_rolling_watch / 前端三副本合起来共**四套**硬编码，措辞互不一致 —— `inclusive_tax`
#   在这里被写成「小微企业普惠税费」、`overseas` 被写成「留学/海外青年人才」，于是同一条
#   政策在 API 元信息、C 端成品、Web 政策库三处的栏目名各不相同（客户看到「B 端政策混进个人清单」）。
#   收敛后本文件**不再持有任何域名文案**，只派生。由 tests/test_domain_labels.py::DL3 守。
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import mappers as M  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.db")
DISCLAIMER = "本仓库不附带任何政策数据：数据目录初始为空，政策条目由使用者自行采集并填入，其准确性、时效性与合规性由数据提供方负责。匹配结果是按结构化字段做的规则估算，不构成申报、办理或入选承诺；真实政策请以当地政府官方发布的最新文件及经办窗口审核为准，办理前可拨当地 12345 政务服务便民热线。"

app = FastAPI(title="政策智能匹配 API", version="0.1.0",
              description="就业创业补贴 / 落户通道 / 人才引进 统一匹配只读接口（数据由使用者自行采集填入，本仓不附带政策数据）")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_CLIENT = os.path.join(_STATIC, "client.html")
if os.path.isdir(_STATIC):
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")


def _load_release():
    """只读「发布记录」（versions 表）：拿最新版本号用于追溯。

    数据本体**不再**从 DB 取 —— 见 _load_source()。
    历史上的坑：本函数原本连 policies 表一起读，于是 /api/v1/match（引擎直读源库）
    与 /api/v1/policies|meta|topic（读 DB 快照）走成了两条数据源，源库一改就脱节
    （实测 414 条 payload 与源库不一致，条数和版本号却完全对得上，光看条数发现不了）。
    """
    if not os.path.exists(DB):
        return None
    conn = sqlite3.connect(DB)
    try:
        ver = conn.execute("SELECT data_version,published_at FROM versions "
                           "ORDER BY data_version DESC LIMIT 1").fetchone()
    except Exception:
        ver = None
    conn.close()
    return ver


def _load_source():
    """P0-1 统一数据源：所有接口都读源库 policy_hub/domains/（唯一真源）。

    复用 server/publish_db.load_all() —— 与发版走的**完全同一套装载 + 同一套
    record_norm 注入**，因此匹配结果与清单/详情/专题永远同版本；
    policy.db 退回「发布记录 + 确权快照」的角色，不再承担读取源。

    source_version = 发布区**全部** *.json 的字节指纹（口径 domains-json-v2）——
    与 publish_db 的 file_digest 同一输入集。C5 修复前它只盖 load_all 的 100 个文件，
    漏掉 catalog.json 等 16 个客户可见文件，导致改了也不"变版本号"。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from publish_db import (load_all as _pub_load_all, file_digest as _pub_file_digest,
                            domain_json_files as _pub_domain_json_files)
    data, _meta, _files, _mism = _pub_load_all()
    idx = {}
    for _dom, items in data.items():
        for it in items:
            idx[it.get("id")] = it
    try:
        digest = _pub_file_digest(_pub_domain_json_files())
    except Exception:
        digest = ""
    return idx, digest


VER = _load_release()
DATA_VERSION, PUBLISHED_AT = (VER[0], VER[1]) if VER else ("v-source", "")
POL, SOURCE_DIGEST = _load_source()
TOPICS_PATH = os.path.join(ROOT, "policy_hub", "topics", "topics.json")
def _load_topics():
    if os.path.exists(TOPICS_PATH):
        return json.load(open(TOPICS_PATH, encoding="utf-8"))
    return {"topics": []}
TOPICS = _load_topics()

# 城市码 -> 城市名（取自 schema.city_code），用于 /meta 城市清单；支撑前端城市下拉数据驱动
# ★ 2026-10-15：展示顺序**直接取 schema.city_code 的键序**（= 城市码登记顺序 = 队列优先级），
#   不再维护第二份手写清单 —— 手写清单必腐（早期手写码表曾漏登一个已注册城市码，
#   被 `ordered` 的兜底排到最后，客户在首页下拉里看到它孤零零挂在末尾；后续批量新增同理）。
#   守：tests/test_city_onboarding.py::test_rc8。
def _load_city_codes():
    p = os.path.join(ROOT, "policy_hub", "common", "schema.json")
    try:
        s = json.load(open(p, encoding="utf-8"))
        def find(o):
            if isinstance(o, dict):
                if isinstance(o.get("city_code"), dict):
                    return o["city_code"]
                for v in o.values():
                    r = find(v)
                    if r:
                        return r
            return None
        return find(s) or {}
    except Exception:
        return {}

CITY_CODE = _load_city_codes()

def _city_of(p):
    c = p.get("city")
    if c:
        return c
    i = p.get("id", "")
    if i.startswith("POL-SZ"):
        return "SZ"
    pre = i.split("-")[0]
    return pre if pre in CITY_CODE else "SZ"


class MatchIn(BaseModel):
    profile: Dict[str, Any] = {}
    brand: Optional[Dict[str, Any]] = None


def _city_rollup(ccnt):
    """城市清单 rollup：按 `schema.city_code` 键序排（= 登记顺序 = 队列优先级），未知码兜底追加末尾。

    ★ 纯函数，供 `build_meta()`（全库）与 `list_policies()`（**按域筛选结果**）**共用同一判据**。
      2026-10-16：此前只有 `build_meta` 有一份，`/api/v1/policies` 不返回城市清单，
      逼得前端「技能培训独立页」只能拿 `CITY_FIELDS[c].domains` 去**猜**哪些城有数据 ——
      有的城已采培训记录，却因声明里没有 `vocational_training` 被下拉静默剔除
      （「数据在库里、客户在界面上选不到」）。
    """
    ordered = ([c for c in CITY_CODE if ccnt.get(c)]
               + sorted(c for c in ccnt if c not in CITY_CODE))
    return [{"code": c, "name": (CITY_CODE.get(c, c) or c).rstrip("市"), "count": ccnt[c]}
            for c in ordered]


def build_meta():
    import collections
    def dom_of(p):
        if p.get("domain"):
            return p["domain"]
        i = p.get("id", "")  # 条目缺 domain 时按 ID 域码兜底
        seg = i.split("-")[1] if i.count("-") >= 1 else ""
        return {"HK": "hukou", "OS": "overseas", "ES": "enterprise_support", "TX": "inclusive_tax"}.get(seg, "")
    cnt = collections.Counter(dom_of(p) for p in POL.values())
    ccnt = collections.Counter(_city_of(p) for p in POL.values())
    cities = _city_rollup(ccnt)
    rtypes = {"employment_startup": "money", "hukou": "channel",
              "overseas": "review", "enterprise_support": "money",
              "housing": "channel", "tech_enterprise": "money", "gba_tax": "money",
              "vocational_training": "money",
              "inclusive_tax": "money"}
    order = ["employment_startup", "enterprise_support", "tech_enterprise", "vocational_training", "inclusive_tax", "housing", "hukou", "gba_tax", "overseas"]
    # ★ label / desc 一律**派生**自 `pipeline/enum_map.json`（唯一真值源），本文件不再持有域名文案。
    domains = {k: {"result_type": rtypes.get(k, "money"),
                   "count": cnt.get(k, 0),
                   "label": M.t("domain", k) or k,
                   "short": M.domain_short(k) or k,
                   "desc": M.domain_desc(k)} for k in order if cnt.get(k, 0)}
    if not cnt:
        # ★ 空库（本仓默认状态）：九个域照样全量返回、count 全 0 ——
        #   否则前端域导航空成一片，看起来像坏掉，而不是「还没填数据」。
        domains = {k: {"result_type": rtypes.get(k, "money"), "count": 0,
                       "label": M.t("domain", k) or k,
                       "short": M.domain_short(k) or k,
                       "desc": M.domain_desc(k)} for k in order}
    districts = sorted({p.get("district") for p in POL.values() if p.get("level") == "district" and p.get("district")})
    # ★ 库为空时上面的字典一个域都没有（按 cnt 过滤）⇒ 直接索引 overseas 会 KeyError。
    #   overseas 的 districts_covered 是前端「区级覆盖」提示用的，空库给空数组即可。
    if "overseas" not in domains:
        domains["overseas"] = {"result_type": "review", "count": 0,
                               "label": M.t("domain", "overseas") or "overseas",
                               "short": M.domain_short("overseas") or "overseas",
                               "desc": M.domain_desc("overseas")}
    domains["overseas"]["districts_covered"] = districts
    return {"city": "", "data_version": DATA_VERSION, "published_at": PUBLISHED_AT,
            "source_version": SOURCE_DIGEST,
            "domains": domains, "cities": cities,
            "total_policies": len(POL), "disclaimer": DISCLAIMER}


@app.get("/api/v1/meta")
def meta():
    return build_meta()


def _brief(pid):
    p = POL.get(pid, {})
    return {
        "id": pid, "name": p.get("name", ""), "result_type": p.get("result_type"),
        "valid": p.get("valid", "active"), "depth": p.get("depth"),
        "material_count": p.get("material_count") or len(p.get("materials", []) or []),
        "guide_url": p.get("guide_url", ""), "source_doc": p.get("source_doc", ""),
    }


def run_match(profile):
    r = aggregate(profile or {})
    # 命中/接近项附完整政策字段，供前端直接渲染卡片；引擎计算字段(status/missing/score等)优先，不被数据字段覆盖
    def attach(x, eng_keys):
        payload = dict(POL.get(x["id"], {}))
        amount_value = x.get("amount")
        merged = dict(payload)       # 1 先放政策完整字段（amount 为规则对象）
        merged.update(x)             # 2 引擎结果覆盖（status/missing/数值amount 等）
        if "amount" in payload:      # 3 amount 保留规则对象供前端分步测算，测算数值另存
            merged["amount"] = payload["amount"]
            merged["amount_value"] = amount_value
        for k in eng_keys:           # 4 引擎决策字段强制优先（防止被 payload 的同名 status 覆盖）
            if k in x:
                merged[k] = x[k]
        if merged.get("materials") is not None:  # 材料数兜底
            merged["material_count"] = merged.get("material_count") or len(merged.get("materials") or [])
        return merged
    emp = r["domains"]["employment_startup"]
    for key in ("match", "near", "exited_or_renamed"):
        emp[key] = [attach(x, ("status", "missing")) for x in emp.get(key, []) or []]
    ov = r["domains"]["overseas"]
    for key in ("match", "near"):
        ov[key] = [attach(x, ("status", "missing")) for x in ov.get(key, []) or []]
    hk = r["domains"]["hukou"]
    hk["decisions"] = [attach(d, ("status", "missing", "branch_hit", "score", "approval_type"))
                       for d in hk.get("decisions", []) or []]
    for dk in ("enterprise_support", "housing", "tech_enterprise", "gba_tax", "inclusive_tax", "vocational_training"):
        dx = r["domains"].get(dk)
        if dx:
            for key in ("match", "near", "exited_or_renamed"):
                if key in dx:
                    dx[key] = [attach(x, ("status", "missing")) for x in dx.get(key, []) or []]
    return {"data_version": DATA_VERSION, "published_at": PUBLISHED_AT,
            "source_version": SOURCE_DIGEST,
            "summary": r["summary"], "domains": r["domains"], "disclaimer": DISCLAIMER}


@app.post("/api/v1/match")
def match(body: MatchIn):
    return run_match(body.profile or {})


@app.get("/api/v1/topics")
def topics():
    out = []
    for t in TOPICS.get("topics", []):
        ids = t.get("policy_ids", [])
        out.append({"key": t["key"], "name": t["name"], "audience": t.get("audience", ""),
                    "desc": t.get("desc", ""), "count": len(ids),
                    "missing": [i for i in ids if i not in POL]})
    return {"data_version": DATA_VERSION, "topics": out}


@app.get("/api/v1/topic/{key}")
def topic_detail(key: str):
    t = next((x for x in TOPICS.get("topics", []) if x["key"] == key), None)
    if not t:
        raise HTTPException(404, "未找到专题包: %s" % key)
    items = []
    for pid in t["policy_ids"]:
        p = POL.get(pid)
        if not p:
            items.append({"id": pid, "missing": True}); continue
        items.append({"id": pid, "name": p.get("name"), "domain": p.get("domain"),
                      "result_type": p.get("result_type"), "depth": p.get("depth"),
                      "valid": p.get("valid", "active"), "ptype": p.get("ptype"),
                      "ptype_detail": p.get("ptype_detail"),
                      "guide_url": p.get("guide_url")})
    return {"data_version": DATA_VERSION, "key": key, "name": t["name"],
            "audience": t.get("audience", ""), "desc": t.get("desc", ""),
            "count": len(items), "items": items, "disclaimer": DISCLAIMER}



def _dom_fallback(pid):
    seg = pid.split("-")[1] if pid.count("-") >= 1 else ""
    return {"HK": "hukou", "OS": "overseas", "ES": "enterprise_support",
            "TX": "inclusive_tax", "VT": "vocational_training"}.get(seg, "")


def _amount_hint(p):
    a = p.get("amount")
    if isinstance(a, dict):
        kind = a.get("kind")
        if kind == "text":
            return a.get("text") or a.get("note", "")
        if a.get("std_name"):
            return a["std_name"]
        if a.get("percent") is not None:
            cap = ("，上限 %s 元" % format(a["cap"], ",")) if a.get("cap") else ""
            return "按基数 %s%% 计算%s" % (a["percent"], cap)
        if a.get("value") is not None:
            return "%s 元 / %s" % (format(a["value"], ","), a.get("unit", "项"))
        m = {"once": "一次性补贴", "once_x_count": "按符合条件人数计发",
             "month_x_count": "按月计发", "per_year_x_count": "按年计发",
             "tiered_hire": "分档计发", "percent_of_base": "按缴费 / 工资基数比例返还",
             "range": "区间定额", "none": "资格 / 通道类"}
        return m.get(kind, "")
    return p.get("std_name", "") or ""


def _win_hint(p):
    w = p.get("apply_window") or {}
    def ok(x):
        return bool(x) and x != "to_collect"
    start, end = w.get("start"), w.get("end")
    if ok(end):
        return ("%s 至 %s" % (start, end)) if ok(start) else ("截止 " + end)
    if w.get("batch") and w["batch"] != "to_collect":
        return w.get("note") or w["batch"]
    note = w.get("note")
    return note if (note and note != "to_collect") else "以当年申报通知为准"


@app.get("/api/v1/policies")
def list_policies(domain: Optional[str] = None, city: Optional[str] = None, q: Optional[str] = None):
    ql = (q or "").strip().lower()
    out = []
    for pid, p in POL.items():
        dom = p.get("domain") or _dom_fallback(pid)
        c = _city_of(p)
        if domain and dom != domain:
            continue
        if city and c != city.upper():
            continue
        if ql and ql not in (p.get("name", "").lower()):
            continue
        out.append({
            "id": pid, "name": p.get("name", ""), "domain": dom, "city": c,
            "result_type": p.get("result_type"), "depth": p.get("depth"),
            "amount_hint": _amount_hint(p), "window": _win_hint(p),
            "source_doc": p.get("source_doc", ""), "guide_url": p.get("guide_url", ""),
            "apply_url": p.get("apply_url", ""),
            "valid": p.get("valid", "active"),
            "deadline": p.get("deadline", ""), "updated_at": p.get("updated_at", ""),
        })
    out.sort(key=lambda x: (x["city"], x["domain"], x["id"]))
    # ★ 城市清单按「本次筛选结果里实际出现的城市」现算（调用方须**不带 city 参数**取它，
    #   否则会退化成只剩那一个城）。前端「域页 / 技能培训页」共用它填下拉
    #   ⇒ 不再靠 `CITY_FIELDS` 声明去猜哪些城有数据（详见 `_city_rollup` 注释）。
    import collections
    return {"data_version": DATA_VERSION, "domain": domain, "city": (city or "").upper(),
            "count": len(out), "items": out,
            "cities": _city_rollup(collections.Counter(x["city"] for x in out))}


@app.get("/api/v1/vt_catalog")
def vt_catalog(city: Optional[str] = None):
    """返回某城市技能培训工种补贴目录（有确定金额的工种）。"""
    c = (city or "SZ").upper()
    path = os.path.join(ROOT, "policy_hub", "domains", "cities", c.lower(),
                        "vocational_training", "catalog.json")
    # 基线城市 SZ 的工种目录在根域目录；其他城市无独立目录时也回退根目录
    if not os.path.exists(path):
        path = os.path.join(ROOT, "policy_hub", "domains",
                            "vocational_training", "catalog.json")
    if not os.path.exists(path):
        return {"city": c, "available": False, "message": "该城市暂未收录工种目录"}
    d = json.load(open(path, encoding="utf-8"))
    return {"city": c, "available": True,
            # 该目录文件属发布区，故带上确权指纹：改动可被 source_version 察觉
            "source_version": SOURCE_DIGEST,
            "catalog_version": d.get("catalog_version"),
            "updated_at": d.get("updated_at"),
            "source_note": d.get("source_note"),
            "level_names": d.get("level_names"),
            "B_confirmed": d.get("B_confirmed", []),
            "special_ability": d.get("special_ability", {}),
            "digital_engineer": d.get("digital_engineer", {}),
            "class_meaning": d.get("class_meaning", {})}


@app.get("/api/v1/policy/{item_id}")
def policy(item_id: str):
    p = POL.get(item_id)
    if not p:
        raise HTTPException(404, "未找到政策条目: %s（当前版本 %s）" % (item_id, DATA_VERSION))
    return {"data_version": DATA_VERSION, "policy": p}


def _line_policy(pid, amount=None):
    p = POL.get(pid, {})
    L = ["● %s" % p.get("name", pid)]
    if amount is not None:
        amt = int(amount) if float(amount).is_integer() else amount
        L.append("  规则估算金额：%s 元（以官方核定为准）" % format(amt, ","))
    std = p.get("std_name")
    if std:
        L.append("  标准：%s" % std)
    mats = p.get("materials") or []
    if mats:
        L.append("  所需材料(%d)：%s" % (len(mats), "；".join(mats)))
    steps = p.get("click_steps") or []
    if steps:
        L.append("  办理步骤：" + " → ".join(steps))
    if p.get("deadline"):
        # ★ deadline 是对象 {mode,text,cycle,trigger,within_months,expire,expire_text}，
        #   直接 json.dumps 会把 `{"type": "text", "text": "长期有效"}` 原样印给客户。
        #   取人读字段：text → expire_text → expire；都没有就说以当年通知为准（不编）。
        dl = p["deadline"]
        if isinstance(dl, str):
            _dltxt = dl
        elif isinstance(dl, dict):
            _dltxt = (dl.get("text") or dl.get("expire_text") or "").strip()
            if not _dltxt and dl.get("expire"):
                _dltxt = "有效期至 %s" % dl["expire"]
        else:
            _dltxt = ""
        L.append("  时效规则：%s" % (_dltxt or "以官方当年申报通知为准"))
    if p.get("guide_url"):
        L.append("  官方入口：%s" % p["guide_url"])
    if p.get("source_doc"):
        L.append("  依据：%s" % p["source_doc"])
    return "\n".join(L)


def run_checklist(profile, brand=None):
    brand = brand or {}
    r = aggregate(profile or {})
    co = brand.get("company", "").strip()
    title = "%s政策申报个性化清单" % (co + " · " if co else "")
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [title, "生成时间：%s　数据版本：%s" % (ts, DATA_VERSION), "=" * 34, ""]
    emp = r["domains"]["employment_startup"]
    hk = r["domains"]["hukou"]
    ov = r["domains"]["overseas"]

    L.append("一、就业创业补贴（命中 %d 项）" % len(emp.get("match", [])))
    if emp.get("match"):
        for x in emp["match"]:
            L.append(_line_policy(x["id"], x.get("amount")))
    else:
        L.append("（按当前画像暂无完全符合项，可补齐条件后再测）")
    L.append("")

    elig = [d for d in hk.get("decisions", []) if d["status"] == "eligible"]
    L.append("二、可走落户通道（%d 条）" % len(elig))
    if elig:
        for d in elig:
            p = POL.get(d["id"], {})
            seg = "● %s" % d["name"]
            if d.get("branch_hit"):
                seg += "（走：%s）" % d["branch_hit"]
            if d.get("score") is not None:
                seg += "　积分预估：%s" % d["score"]
            L.append(seg)
            for k in ("materials", "click_steps", "deadline"):
                v = p.get(k)
                if isinstance(v, list) and v:
                    L.append("  " + ("材料：" if k == "materials" else "步骤：") + ("；".join(v) if k == "materials" else " → ".join(v)))
                elif isinstance(v, str) and v:
                    L.append("  时效：%s" % v)
    else:
        L.append("（当前画像暂无完全满足的通道，可看 /match 返回的 near 项补齐条件）")
    L.append("")

    L.append("三、%s（命中 %d 项，含区级叠加）"
             % (M.t("domain", "overseas"), len(ov.get("match", []))))
    if ov.get("match"):
        for x in ov["match"]:
            L.append(_line_policy(x["id"], x.get("amount")))
    else:
        L.append("（按当前画像暂无完全符合项）")
    L.append("")
    L.append("=" * 34)
    L.append(DISCLAIMER)
    if co:
        L.append("")
        L.append(co)
        if brand.get("contact"):
            L.append("联系方式：%s" % brand["contact"])
    text = "\n".join(L)
    return {"data_version": DATA_VERSION, "title": title,
            "summary": r["summary"], "text": text, "disclaimer": DISCLAIMER}


@app.post("/api/v1/checklist")
def checklist(body: MatchIn):
    return run_checklist(body.profile or {}, body.brand)


LEADS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leads.json")

class LeadIn(BaseModel):
    name: str = ""
    city: str = ""
    contact: str = ""
    source: str = "web"
    note: str = ""


def _read_leads():
    if not os.path.exists(LEADS_FILE):
        return []
    try:
        return json.load(open(LEADS_FILE, encoding="utf-8"))
    except Exception:
        return []


@app.post("/api/v1/leads")
def add_lead(body: LeadIn):
    name = (body.name or "").strip()
    contact = (body.contact or "").strip()
    if not name and not contact:
        raise HTTPException(400, "请至少填写称呼或联系方式")
    leads = _read_leads()
    leads.insert(0, {
        "id": "L" + datetime.datetime.now().strftime("%Y%m%d%H%M%S") + str(len(leads))[-3:],
        "name": name or "（未填称呼）", "city": body.city or "",
        "contact": contact, "source": body.source or "web",
        "note": body.note or "", "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    json.dump(leads, open(LEADS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return {"ok": True, "count": len(leads)}


@app.get("/api/v1/leads")
def list_leads():
    return {"count": len(_read_leads()), "leads": _read_leads()}


def _client_page():
    """客户版 Demo 主页：**直接吐 HTML，绝不做重定向**。

    ★ 2026-10-21 修（线上打开只剩 "Not Found"）：
      原实现 `RedirectResponse("/static/client.html")`。托管平台的网关要求**每一个请求**
      都携带分享凭证（`?sharecode=` 或首次种下的 cookie），而 307 的目标地址是裸
      `/static/client.html`，于是凭证在跳转这一步被丢掉 —— 网关判定匿名，线上直接拦。
      本地 uvicorn 没有这层网关，所以本地永远 200、线上永远失败。
      实测（2026-10-21）：`/?sharecode=X` → 307 → `/static/client.html` → **403**；
      同一地址补回 `?sharecode=X` → **200**。改直出后 URL 恒为 `/`，凭证不离手。
      本地联调入口 `/static/client.html` 仍然保留，两条路径同源同内容。
    """
    return FileResponse(_CLIENT, media_type="text/html; charset=utf-8")


@app.get("/", include_in_schema=False)
def root():
    return _client_page()


@app.get("/index.html", include_in_schema=False)
def index_page():
    # 反代/预览面板有些会直接取 index.html；没有它会掉进下面的 404
    return _client_page()


@app.get("/health", include_in_schema=False)
@app.get("/healthz", include_in_schema=False)
def health():
    # 托管平台的存活探针与人工排查入口；不读数据，避免探针把大库拖起来
    return {"ok": True, "app": "policy-match"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)

# 挂载开放 API（/open/v1，需 X-API-Key，含限流与用量计数）
from server import openapi as _openapi  # noqa: E402
app.include_router(_openapi.router)

# 清单 Excel 导出（/api/v1/export/*）—— ★ 必须注册在下面的兜底路由**之前**，
# 否则会被 `/{full_path:path}` 抢先匹配（兜底对 api/ 前缀抛 404，导出就调不到了）
from server import export_api as _export  # noqa: E402
app.include_router(_export.router)


# ══ 兜底：未知路径一律回落到客户版主页 ══════════════════════════════════
# ★ 2026-10-21（第二轮，紧接“根路径改直出”之后）：只修 `/` 还不够。
#   托管平台的**应用面板 / 预览 iframe 会用它自己拼的路径**去加载页面（不是 `/`），
#   而且这个路径我们事先看不到；路径一不对，原实现就掉进 FastAPI 的 404，
#   线上看到的就是一片 "Not Found"。SPA 兜底把这**一整类**入口问题一次性消掉：
#   除接口前缀外，任何 GET 路径都吐同一份 client.html。
#   ★ 但 `api/` `open/` `static/` **必须继续 JSON 404** —— 否则打错的接口路径会被
#     静默吞成 HTML，前端拿去 JSON.parse 时报 "Unexpected token <"，更难查。
#   注册顺序在最后 ⇒ `/docs`、`/openapi.json`、各 API 路由仍然优先匹配。
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.split("/", 1)[0] in {"api", "open", "static"}:
        raise HTTPException(status_code=404, detail="Not Found")
    return _client_page()
