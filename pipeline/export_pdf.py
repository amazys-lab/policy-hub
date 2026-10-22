# -*- coding: utf-8 -*-
"""
C 端 PDF 导出器 · JSON 规则库 → A4 HTML → Chrome headless → PDF
================================================================
与 B 端 Excel 的分工：
  B 端 = 全量「工具」表（可筛选，卖机构 / B 端个人决策者）
  C 端 = 个人可申报的「读本」（7 字段，卖普通个人）

关键规则：
  1. 源目录全程只读（只 json.load），产物落在本项目 output/ 下
  2. C 端只收录「个人 / 创业者 / 海外人才」可申报的条目（企业专项不进）
  3. 缺字段跳过整行，绝不输出 None / null / 英文枚举
  4. 交付前自检：div 配对 / 封面条数与实际一致 / 英文枚举残留 / 占位符残留

用法：
  python export_pdf.py --city SZ          # 单城（C 端交付单元）
  python export_pdf.py --city SU          # 单城：另一座城市（城市码见 enum_map.city）
  python export_pdf.py --preset prd       # 多城包（配方示例，现多改走 Excel）
  python export_pdf.py --preset all       # 全库包：已收录城市（城市数从数据现算）
  python export_pdf.py --city SZ --src <源目录> --out <输出目录>
"""
import argparse
import collections
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

from jinja2 import Template

from audience import (PERSON_FALLBACK_DOMAINS, PERSON_KINDS,  # noqa: F401
                      is_person, kinds_of)
import cross_city
import geo
import loader
import link_guard as LG
import mappers as M

# L5（2026-10-09）：出成品前链接降级 —— 坏链/错链不渲染成超链接
AUDIT = LG.load_audit()
LINK_STRICT = False      # --link-strict：连栏目/聚合页、解读页、新闻页也降级
DOWNGRADED = []

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL_PATH = os.path.join(HERE, "pdf_template.html")

VERSION = "v20261017"                  # 成品文件名里的版本号：改了数据要自己换一个。
                                       # ★ 必须与 export_excel.VERSION 同号（release_matrix.current_version 会拦分叉）
TODAY = datetime.date.today().isoformat()

# 页脚文案（合规口径与封面/末页一致：只做公开信息整理、不代理申报）。
# 注意：宽度要和「产品名 + 版本」/「第 X / Y 页」拼在一行不重叠 —— 实测 38 字 ≈ 70mm，安全。
FOOTER_NOTE = "本清单为公开政策信息整理，非官方发布；补贴标准与申报条件以官方最新文件及经办窗口答复为准"

CHROME_CANDS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# ── C 端收录口径：只卖个人能申报的 ──────────────────────────────
# ★ 判据真值源 = `pipeline/audience.py`（2026-10-12 抽出）。
#   原因：C 端多城改出 Excel 后，`export_excel.py --audience c` 需要同一判据 ——
#   各写一份就是「两套判据分叉」（两端条数会对不上）。此处只 import，不再定义。

DOMAIN_ORDER = [
    "employment_startup", "vocational_training", "hukou", "housing",
    "overseas", "gba_tax", "inclusive_tax", "enterprise_support", "tech_enterprise",
]

# ★ C 端收录口径里「第三类主体」的文案，与 `enum_map.applicant_kind.overseas` **同源**
#   （2026-10-17 C 项）。此前 `enum_map` 里这一主体叫「海外人才」、而 C 端封面写「留学人才」——
#   同一个判据两种叫法（`audience.PERSON_KINDS` 里它就是 `overseas`）。
#   ★ 为什么不用「人才引进」：域名（域容器）与**申报主体**是两个字段，前者已改为「人才引进」，
#     后者在 `enum_map.applicant_kind` 里的规范名就是「海外人才」—— 各按各自真值源取，不互相串。
OS_KIND = M.t("applicant_kind", "overseas") or "海外人才"
PERSON_SCOPE = "个人 · 创业者 · %s" % OS_KIND
PERSON_SCOPE_SLASH = "个人 / 创业者 / %s" % OS_KIND

# ★ 域中文文案（全名 / 紧凑短名 / 描述句）的唯一真值源 = `pipeline/enum_map.json`
#   （`domain` / `domain_short` / `domain_desc` 三表，键集完全相等），经 `M.t("domain")`、
#   `M.domain_short()`、`M.domain_desc()` 派生。
#   2026-10-17（C 项）：此前本文件另立 `DOMAIN_DESC` / `DOMAIN_SHORT` 两张硬编码表，
#   与 `enum_map` / `server/app.py` / `build_rolling_watch` / 前端三副本合起来共**四套**，
#   措辞互不一致 —— `overseas` 在这里叫「留学人才」、在 app.py 叫「留学/海外青年人才」、
#   在前端卡片叫「留学 / 海外青年人才」。收敛后本文件**不再持有域名文案**，只派生。
#   由 `tests/test_domain_labels.py::DL4` 守（含「本文件不得再出现域名文案字面量」的反向断言）。
# 类别短名（2026-10-12）：目录「城市行」右侧的类别速览要在一行里放下 5~7 个类别，
# 全名（如「大湾区个税补贴」6 字）会撑爆行宽，故短名独立成表 —— 但同一份真值源。
# ⚠️ 只用于紧凑位（目录速览 / 章头速览），卡片与章标题仍用全名。

# ── 三档产品 ───────────────────────────────────────────────────
# ── 单城产品：**现算**，不硬编码城市清单（2026-10-14）──────────────────────
# 「一城一 PDF」是 C 端的单城交付单元 —— 读者关心的是「我这座城市能领什么」，
# 不是区域打包清单，所以每座有货的城市都该有一本自己的册子。
#
# ★ 为什么用**现算函数**而不是在 PRODUCTS 里硬编码 N 条：
#   城市清单会随采集增长。写死 ⇒ 新增城市后这本册子
#   不会自动出现，且名字 / 清单一起腐（§5x：「凡会随采集增长的，一律不写死」）。
# ★ 城市名取自 `mappers.city()`，不手抄 —— 城市码有**五个注册点**（§5s），
#   任何一处漏写都会让封面印出英文码（**客户可见**）。
CITY_PREFIX = "city_"
_CITY_CACHE = {}     # code → 产品定义。★ 保证同一 code 恒返回**同一对象**：
                     #   `test_output_sync` 的 `RM.pdf_meta(p) is EP.resolve_preset(p)` 是 identity 断言。


def city_product(code):
    """单城产品定义（`code` 如 "SZ"）。未注册的城市码**直接报错**，不静默出一本空册子。"""
    code = str(code).upper()
    if code in _CITY_CACHE:
        return _CITY_CACHE[code]
    name = M.city(code)
    if not name or name == code:
        # mappers 对未注册的值**原样返回** —— 那就等于"这个城市码没人认领"（§5s 五注册点）
        raise KeyError("城市码 %r 未在 enum_map.city 注册（§5s：城市码有五处注册点）" % code)
    prod = dict(
        title="%s个人补贴清单" % name,
        subtitle=PERSON_SCOPE + " 可申报",
        scope="%s市" % name,
        cities=[code],
        fname="%s个人补贴清单" % name,
    )
    _CITY_CACHE[code] = prod
    return prod


def resolve_preset(name):
    """preset 名 → 产品定义。静态 `PRODUCTS[...]` 或现算的 `city_<城市码>`。

    ★ 单城产品**不预先物化**进 `PRODUCTS`（物化 = 把会增长的城市数写死）。
      但 `PRODUCTS["sz"]` 本身就由 `city_product("SZ")` 生成、走同一个缓存，
      所以 `PRODUCTS["sz"] is resolve_preset("city_sz")` 成立（identity 断言过得去）。
    """
    if name.startswith(CITY_PREFIX):
        return city_product(name[len(CITY_PREFIX):].upper())
    return PRODUCTS[name]


PRODUCTS = {
    "sz": city_product("SZ"),          # 单城入口产品（示例：SZ）—— 与单城产品**同一对象**
    "prd": dict(
        title="珠三角9市个人补贴清单",
        subtitle="深圳·广州·东莞·佛山·中山·珠海·江门·肇庆·惠州",
        scope="广东省珠三角九市（深圳、广州、东莞、佛山、中山、珠海、江门、肇庆、惠州）",
        cities=["SZ", "GZ", "DG", "FS", "ZS", "ZH", "JM", "ZQ", "HZ"],
        fname="珠三角9市个人补贴清单",
    ),
    "gd_prov": dict(
        title="广东省个人补贴清单",
        subtitle=PERSON_SCOPE + " 可申报",
        # scope 会在 main 里被覆盖率文案覆盖（诚实标注已收录几个地级市）
        scope="广东省",
        cities=["SZ", "GZ", "DG", "FS", "ZS", "ZH", "JM", "ZQ", "HZ"],
        fname="广东省个人补贴清单",
        # province 非空 → 启用「跨城归并 + 覆盖率标注」（与 B 端 export_excel 同源判据）
        province="广东",
    ),
    "all": dict(
        # ★ 2026-10-13 两次改名：「全国14城个人补贴清单」→「全国个人补贴清单」→ 本名。
        #   第一次（`63-`）：原名把**会随采集增长的城市数**写进产品名
        #   （印在封面 / 文件名 / `release_matrix` 里），新增城市后实际 15 城 ⇒ 名字失真。
        #     判据：**凡会随采集增长的技术／清单，一律不写死**。
        #   第二次（`65-`）：去掉「全国」—— 库里只有 **4 省 15 城**，名字自称的地理范围
        #   **无数据支撑**。这是与「数字会腐」并列的另一类：**地理主张也得有据**
        #   （判据实现 `export_excel.check_title_scope`，B/C 两端共用）。
        #   覆盖城市清单仍由 `coverage_scope_text()` 从数据现算（见 main）。
        #   固定地理口径（珠三角 9 市 = 官方定义）不属于会腐计数／无据主张，可保留。
        title="已收录城市个人补贴清单",
        subtitle="珠三角 · 长三角 · 广西　" + PERSON_SCOPE_SLASH + " 可申报",
        scope="已收录城市",                 # 由 main() 依实际收录城市现算覆盖
        cities=None,
        fname="已收录城市个人补贴清单",
    ),
}


def coverage_scope_text(recs):
    """多城产品的「覆盖范围」文案 —— **按省分组列出实际收录的城市**（现算，不写死清单）。

    事故（2026-10-13）：`all` 产品的 `subtitle` / `scope` 曾写死
    「珠三角9市 · 长三角4市 · 广西南宁」并把产品名定为「全国14城个人补贴清单」。
    2026-10 新增城市后实际 **15 城** → 产品名、副标题、封面口径**同时失真**。
    ⇒ 判据：**凡会随采集增长的城市数 / 城市清单，一律从数据现算**（与「条数绝不硬编码」同源）。
       固定地理口径（「珠三角 9 市」= 官方定义）不属于会腐的计数，可写死。
    """
    by_prov = {}
    for r in recs:
        p = M.province(r.get("city", "")) or "其他"
        nm = M.city(r.get("city", ""))
        lst = by_prov.setdefault(p, [])
        if nm and nm not in lst:
            lst.append(nm)
    parts = ["%s：%s" % (p, "、".join(cs))
             for p, cs in sorted(by_prov.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    n_city = sum(len(v) for v in by_prov.values())
    return "全国 %d 个城市（%s）" % (n_city, "；".join(parts))


# ══ 工具函数 ══════════════════════════════════════════════════
CARD_SRC_MAX = 44          # C 端卡片「政策依据」行可见窗口（口径句必须落在此窗口内，
                           # 见 mappers.clip_note_visible；卡片按「~11 行 / 单页 4~5 条」设计）


def _clip(s, n, tail="…"):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n].rstrip("，,；;、 ") + tail


def _strip_urls(s):
    return re.sub(r"https?://\S+", "", str(s or ""))


def find_chrome():
    for p in CHROME_CANDS:
        if os.path.exists(p):
            return p
    return None


CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"


def _channel_note(rec, max_len=52):
    """渠道说明：按分句截断，并清掉「直达办事指南：」这类被剥掉 URL 后的悬空引导语。

    ★ 取值走 `M.channel_note()`（与 B 端 Excel **同源**），本函数只负责截断与清洗。
    """
    raw = _strip_urls(M.channel_note(rec))
    raw = re.sub(r"(；|;|,|，)?\s*(直达办事指南|办事指南|政策依据|办理入口|申报入口|官方入口|原文件|详见|见)\s*[：:]\s*$", "", raw.strip())
    out = ""
    for p in re.split(r"(?<=[；;。])", raw):
        if not p.strip():
            continue
        if out and len(out) + len(p) > max_len:
            break
        out += p
        if len(out) >= max_len * 0.7:
            break
    out = out.strip(" ；;。，,、")
    return out or _clip(raw, max_len)


def _conditions_line(rec, max_items=3, max_len=88):
    """申报条件：按条贪心填充到一行，宁少一条也不在词中间截断。

    ★ 条目来源 = `mappers.condition_items()`（2026-10-12 收敛）：旧版此处**自己读**
      `rec["cond"]["must"]`，与 `mappers.conditions_text()` 构成第二份判据 ——
      实测两者漏读集合完全一致（各 193 条空白）却要改两处。
      同源后，PDF 与 Excel 的「申报条件」不可能再出现一份修好另一份还空的情况。
    """
    labels = [x for x in (_clip(x, 42) for x in M.condition_items(rec)) if x]
    if not labels:
        return ""
    chosen, used = [], 0
    for p in labels:
        add = len(p) + (1 if chosen else 0)
        if len(chosen) >= max_items or (chosen and used + add > max_len):
            break
        chosen.append(p)
        used += add
    s = "；".join(chosen)
    if len(chosen) < len(labels):
        s += f"　等{len(labels)}项"
    return s


def _materials_line(rec, max_items=5, max_len=86):
    """申报材料：圈码内联成一行，比逐行排省 4~6 行高度。"""
    ms = rec.get("materials")
    if not isinstance(ms, list):
        return ""
    ms = [_clip(x, 18) for x in ms if str(x).strip()]
    if not ms:
        return ""
    chosen, used = [], 0
    for i, m in enumerate(ms):
        if len(chosen) >= max_items:
            break
        p = f"{CIRCLED[i]}{m}"
        if chosen and used + len(p) + 1 > max_len:
            break
        chosen.append(p)
        used += len(p) + 1
    s = "　".join(chosen)
    if len(chosen) < len(ms):
        s += f"　等{len(ms)}项"
    return s


def _steps_line(rec, max_items=2, each=32):
    """办理步骤：前两步足以让人知道「从哪儿下手」，压到一行内。"""
    cs = rec.get("click_steps")
    if not isinstance(cs, list):
        return ""
    cs = [_clip(x, each) for x in cs if str(x).strip()]
    if not cs:
        return ""
    return "　→　".join(f"{CIRCLED[i]}{s}" for i, s in enumerate(cs[:max_items]))


def build_card(rec, no_width):
    """把一条政策记录转成 C 端卡片视图。

    C 端 = 阅读品，一条控制在 ~11 行内（约 60mm），单页 4~5 条。
    完整条款不在这里复现 —— 需要全字段的是 B 端 Excel，不是这本读本。
    """
    name = str(rec.get("name") or "").strip()

    kinds = kinds_of(rec)
    meta_bits = []
    if kinds:
        meta_bits.append(" / ".join(M.t("applicant_kind", k) for k in
                                   [x for x in ("person", "entrepreneur", "overseas", "family") if x in kinds]))
    for field in ("result_type", "approval_type"):
        v = M.t(field, rec.get(field))
        if v:
            meta_bits.append(v)

    amount = M.amount_text(rec)
    is_money = bool(re.search(r"\d", amount))

    ch = M.t("channel", rec.get("channel"))
    channel_line = " · ".join([x for x in (ch, _channel_note(rec)) if x])

    window = M.apply_window_text(rec)
    dl = M.deadline_text(rec)

    def _n(s):
        return re.sub(r"[\s，,；;、。]+", "", str(s or ""))

    # 有效期与申报窗口同文时只留一次（deadline_text 常是 apply_window 的后半句）
    if window and dl and (_n(dl) == _n(window) or _n(dl) in _n(window)):
        dl = ""
    if dl.startswith("长期有效") and not window:
        window, dl = dl, ""

    # 两个时间字段并成一行显示：申报窗口 ｜ 有效期
    timing = "　｜　".join([x for x in (_clip(window, 56), _clip(dl, 40)) if x])

    url = M.original_doc_url(rec, AUDIT)
    entry = M.entry_url(rec)
    if entry == url:
        entry = ""
    # L5：坏链/错链降级（模板 {% if c.url %} 已有兜底 —— 置空即不渲染超链接，只留文号）
    _g, _e, _notes = LG.degrade({"guide_url": url, "apply_url": entry}, AUDIT, LINK_STRICT)
    if _notes:
        DOWNGRADED.append((rec.get("id", ""), LG.note_text(_notes), url or entry))
        url, entry = _g, _e

    src = M.source_doc(rec)
    if "原文见办理入口" in src or "来源见办理入口" in src:
        m = re.match(r"https?://([^/]+)", url)
        src = f"来源站点：{m.group(1)}" if m else ""

    return {
        "no": "",
        "id": str(rec.get("id") or ""),
        "name": name,
        # 方案 B（2026-10-12）：多城产品标注**适用范围** —— 省级/国家级政策被各市各录一条时，
        # 读者能一眼看出「这不是重复，是同一条政策在 9 个市各存了一份」。
        # 判据来自 `cross_city.annotate_scope()`（与省表归并同源），此处只做文案映射。
        "scope_label": rec.get("_scope_label") or "",
        "tag": M.t("domain", rec.get("domain")) or "",
        "meta_line": "　·　".join([x for x in meta_bits if x]),
        "amount": _clip(amount, 96),
        "amount_is_money": is_money,
        "conditions": _conditions_line(rec),
        "materials_line": _materials_line(rec),
        "channel_line": channel_line,
        "steps_line": _steps_line(rec),
        "timing": timing,
        "window": _clip(window, 56),
        "deadline": _clip(dl, 44),
        # C 端窗口仅 44 字：口径句若被截在窗口外，客户会把省级原文档成本级政策
        # → 用 note-aware 裁剪（窗口平移，不删内容）
        "source_doc": M.clip_note_visible(src.replace("（原文见办理入口）", ""), CARD_SRC_MAX),
        "url": url,
        "entry": entry,
    }


def db_version(src):
    p = os.path.join(src, "policy_hub", "common", "domains_meta.json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        for k in ("version", "release", "data_version"):
            if d.get(k):
                return str(d[k])
    except Exception:
        pass
    return "unknown"


def source_stats(recs):
    """返回 (来源说明文案, 来源站点数, 官方域名站点数)。

    ⚠️「官方域名」判据真值源 = `link_guard.is_official_host()`（2026-10-10 收口）。
    此处原为 `h.endswith("gov.cn")` —— 会把**政策原文指定的非 .gov.cn 官方入口**
    （如广西数智人社 `www.gx12333.net`，见 45- 报告 §2）漏算成"非官方"。
    **不在此另写一份判据**（本项目已因"两套判据分叉"踩过 4 次）。
    """
    hosts = collections.Counter()
    for r in recs:
        for u in (r.get("sources") or []):
            if isinstance(u, str) and u.startswith("http"):
                m = re.match(r"https?://([^/]+)", u)
                if m:
                    hosts[m.group(1).lower()] += 1
        for k in ("guide_url", "apply_url"):
            m = re.match(r"https?://([^/]+)", str(r.get(k) or ""))
            if m:
                hosts[m.group(1).lower()] += 1
    n = len(hosts)
    gov = sum(1 for h in hosts if LG.is_official_host(h))
    txt = (f"人力资源社会保障、税务、住房和城乡建设等主管部门门户网站，"
           f"共 {n} 个来源（其中 {gov} 个为官方域名）")
    return txt, n, gov


def data_asof(recs):
    """数据时点 = 收录条目里最新的核验日期。"""
    days = [str(r.get("updated_at") or "").strip() for r in recs]
    days = [d for d in days if re.match(r"^\d{4}-\d{2}-\d{2}$", d)]
    return max(days) if days else TODAY


# ══ 主体 ══════════════════════════════════════════════════════
def build_html(recs, prod, src=None, all_rows=None):
    """把记录渲染成 A4 HTML。返回 (html, stats)。

    `all_rows` = **全库** active 记录，用于「适用范围」层级判定
    （`cross_city.annotate_scope()` 必须跳出本表范围才能区分国家级 vs 省级，见其 docstring）。
    """
    recs = [r for r in recs if is_person(r)]

    # 适用范围标注（方案 B）：仅多城产品启用 —— 单城清单里每条都是同一座城，标了是噪音。
    _cities = prod.get("cities")
    multi_city = (_cities is None) or (len(_cities) > 1)
    if multi_city:
        # 文案映射真值源 = `cross_city.scope_labels()`（C 端 Excel 用同一份，见其 docstring）
        _labels = cross_city.scope_labels(recs, all_rows or recs, prod.get("province"))
        for r in recs:
            r["_scope_label"] = _labels.get(r.get("id")) or (M.city(r.get("city")) or "")

    # ── 排序与分组（2026-10-12 改「城市优先」）─────────────────────
    # 为什么改：原按补贴类别分章 —— 多座城市混在同一章里，读者想找「某城的落户政策」
    #   要在「落户通道」章里逐条筛城市（实测该章跨 9 城）。改成**先城市、后类别**后，
    #   翻到「该城」章就是一片自足的小世界；章内再用类别分小节。
    # 城市顺序：条数降序。并列时按 `PRODUCTS.cities` 声明序、再按城市码兜底 ——
    #   写死次序保证**确定性**（不依赖 Counter 的隐式顺序，也不做字典序的随机感）。
    _city_seq = list(prod.get("cities") or [])
    _n_by_city = collections.Counter(r["city"] for r in recs)
    _city_order = sorted(
        _n_by_city,
        key=lambda c: (-_n_by_city[c],
                       _city_seq.index(c) if c in _city_seq else 99,
                       str(c)))

    _dom_no = {d: i for i, d in enumerate(DOMAIN_ORDER)}

    def _amt_key(r):
        _lo, _hi = M.amount_low_high(r)
        return (0 if _hi else 1, -(_hi or 0), str(r.get("name") or ""))

    if multi_city:
        recs.sort(key=lambda r: (_city_order.index(r["city"]),
                                 _dom_no.get(r["domain"], 99), _amt_key(r)))
    else:
        recs.sort(key=lambda r: (_dom_no.get(r["domain"], 99), _amt_key(r)))

    width = 3 if len(recs) >= 100 else 2
    for i, r in enumerate(recs, 1):
        r["_no"] = str(i).zfill(width)

    def _mk_sections(items):
        """把一批记录按补贴类别切成小节（多城产品用在城市章内部）。"""
        g = collections.OrderedDict()
        for r in items:
            g.setdefault(r["domain"], []).append(r)
        secs = []
        for dom, its in g.items():
            cards = []
            for r in its:
                c = build_card(r, width)
                c["no"] = r["_no"]
                cards.append(c)
            secs.append({
                "key": dom,
                "name": M.t("domain", dom) or dom,
                "short": M.domain_short(dom) or M.t("domain", dom) or dom,
                "desc": M.domain_desc(dom),
                "count": len(cards),
                # 目录「章节导航」用（2026-10-12）：该章/节的**编号区间**。
                # 为什么不用页码：页码由 Chrome 分页决定，HTML 阶段拿不到；
                # 而正文每张卡片都带编号，读者按编号区间即可定位，等价且不依赖渲染。
                # ⚠️ 这个串同时是 **PDF 书签的定位锚点**（见 write_bookmarks）：
                #    「编号 064–095」全文唯一（目录里不带「编号」二字），改动措辞会让书签失锚。
                "no_from": cards[0]["no"] if cards else "",
                "no_to": cards[-1]["no"] if cards else "",
                # 注意：键名不能叫 items —— jinja2 里 ch.items 会解析成 dict.items 方法
                "cards": cards,
            })
        return secs

    if multi_city:
        chapters = []
        for city in _city_order:
            secs = _mk_sections([r for r in recs if r["city"] == city])
            _cname = M.city(city) or city
            for s in secs:
                for c in s["cards"]:
                    # 城市章内，卡片「适用范围」= 本章城市时是冗余（整章都是这座城）；
                    # 只保留真正提供信息的上级政策标注（「{省}全省」「全国通用」）。
                    # 2026-10-12：徽标从"每条都要看"变成"只在跨级时出现"，卡片头更干净。
                    if c.get("scope_label") == _cname:
                        c["scope_label"] = ""
            cards = [c for s in secs for c in s["cards"]]
            chapters.append({
                "is_city": True,
                "key": city,
                "name": _cname,
                "count": len(cards),
                "no_from": cards[0]["no"] if cards else "",
                "no_to": cards[-1]["no"] if cards else "",
                # 章头右侧速览：读者一眼看到「这座城市有哪些类别、各多少条」
                "sec_line": "　".join(f"{s['short']} {s['count']}" for s in secs),
                "sections": secs,
                # 保留 `toc` 明细（本版目录不再逐条渲染，留作数据侧备用/未来检索）
                "toc": [{"no": c["no"], "name": c["name"], "scope": c.get("scope_label") or ""}
                        for c in cards],
            })
    else:
        # 单城产品：保持原「按类别分章」的一维结构 —— 只有一座城时，城市维度没有信息量
        # （用户实测反馈：单城 PDF 现在这样就好用），不要为了"统一"给它套一层城市章。
        chapters = []
        for s in _mk_sections(recs):
            s["is_city"] = False
            s["toc"] = [{"no": c["no"], "name": c["name"], "scope": c.get("scope_label") or ""}
                        for c in s["cards"]]
            chapters.append(s)

    depths = collections.Counter(str(r.get("depth") or "?") for r in recs)
    depth_line = "　".join(f"{M.t('depth', k)} {v} 条" for k, v in sorted(depths.items()))

    src_txt, n_host, n_gov = source_stats(recs)
    city_n = len(set(r["city"] for r in recs))

    # 目录「按城市查找」表（多城产品的主索引，2026-10-12）。
    # 它取代了上一版的「各市条目数」速览条 —— 城市从"一句速览"升级为**可定位的索引**：
    # 每行给出条数 + 编号区间，读者据此直接翻到该城。
    city_index = ([{"name": ch["name"], "n": ch["count"],
                    "no_from": ch["no_from"], "no_to": ch["no_to"],
                    "sec_line": ch["sec_line"]} for ch in chapters]
                  if multi_city else [])

    # 目录「按补贴类别」网格（次索引）：类别仍是有效入口（"我想看所有城市的落户政策"），
    # 但不作为主结构 —— 故只给条数与覆盖城市数，不给编号区间（跨城市不连续，给了反而误导）。
    _dom_cnt = collections.Counter(r["domain"] for r in recs)
    _dom_city = collections.defaultdict(set)
    for r in recs:
        _dom_city[r["domain"]].add(r["city"])
    domain_index = [{"name": M.t("domain", d) or d,
                     "short": M.domain_short(d) or M.t("domain", d) or d,
                     "n": _dom_cnt[d], "city_n": len(_dom_city[d]),
                     "desc": M.domain_desc(d)}
                    for d in sorted(_dom_cnt, key=lambda d: _dom_no.get(d, 99))]

    # 封面数字块：多城产品第一维度是**城市**（读者先选城、再选类别），故第二位放「覆盖城市」；
    #   单城产品城市恒为 1、没有信息量（"覆盖城市 1"），第二位仍是「补贴类别」、第三位给来源站点。
    if multi_city:
        stat2_value, stat2_label = str(city_n), "覆盖城市"
        stat3_value, stat3_label = str(len(_dom_cnt)), "补贴类别"
    else:
        stat2_value, stat2_label = str(len(chapters)), "补贴类别"
        stat3_value, stat3_label = str(n_host), "官方来源站点"

    meta = {
        "title": prod["title"],
        "subtitle": prod["subtitle"],
        "scope": prod["scope"],
        # ★ 末页「本清单收录 … 可以申报」的口径句也从真值源来（2026-10-17 C 项）。
        #   此前它是 `pdf_template.html` 里的**硬编码**「个人 / 创业者 / 留学人才」——
        #   第六处同名不同源（封面 subtitle 改了、末页没改 ⇒ 同一本册子两种说法）。
        "person_scope": PERSON_SCOPE_SLASH,
        "count": len(recs),
        "chapter_count": len(chapters),
        "city_count": city_n,
        "multi_city": multi_city,
        "stat2_value": stat2_value,
        "stat2_label": stat2_label,
        "stat3_value": stat3_value,
        "stat3_label": stat3_label,
        "sources": src_txt,
        "date": TODAY,
        "version": VERSION,
        "data_asof": data_asof(recs),
        "db_version": db_version(src or loader.DEFAULT_SRC),
        "depth_line": depth_line,
        # 目录表（多城产品渲染两张索引；单城为空 → 模板回落为原「按类别」一行一章）
        "city_index": city_index,
        "domain_index": domain_index if multi_city else [],
        # 省表专属：归并说明（诚实告知"未逐条标注适用城市"）
        "merge_note": prod.get("merge_note", ""),
        # 多城产品专属：逐条标适用范围的说明（方案 B）。省表已归并，说明由 merge_note 承担。
        "scope_note": (
            "本清单已逐条标注适用范围：标「某市」的是该市本级政策；标「某省全省」「全国通用」的"
            "是上级政策 —— 这类政策各省市会各自发布一次，内容相同，本清单按城市分别列出、未做归并。"
            if (multi_city and not prod.get("merge_note")) else ""),
    }

    with open(TPL_PATH, encoding="utf-8") as f:
        tpl = Template(f.read(), autoescape=True)
    html = tpl.render(meta=meta, chapters=chapters)

    # 扁平化取所有卡片：单城 chapters 就是"类别节"本身；多城 chapters 是城市、卡片在 sections 里。
    _all_cards = [c for ch in chapters
                  for s in (ch.get("sections") or [ch])
                  for c in s["cards"]]
    stats = {
        "count": len(recs),
        "chapters": len(chapters),              # 单城 = 类别数；多城 = 城市数
        "sections": sum(len(ch.get("sections") or []) for ch in chapters),
        "multi_city": multi_city,
        "city_count": city_n,
        "by_domain": {M.t("domain", d) or d: n for d, n in
                      sorted(_dom_cnt.items(), key=lambda x: _dom_no.get(x[0], 99))},
        # 章头清单（用于控制台报告与 PDF 书签）—— 只带定位必需字段，不带卡片，避免拖大 stats
        "chapters_meta": [{"name": ch["name"], "count": ch["count"],
                           "no_from": ch["no_from"], "no_to": ch["no_to"],
                           "sections": [{"name": s["name"], "count": s["count"],
                                         "no_from": s["no_from"], "no_to": s["no_to"]}
                                        for s in (ch.get("sections") or [])]}
                          for ch in chapters],
        "no_url": [c["id"] for c in _all_cards if not c["url"]],
    }
    return html, stats


BAD_TOKENS = [
    ">None<", ">none<", ">null<", "to_collect", "NoneNone",
    ">unit<", ">online<", ">window<", ">mixed<", ">money<", ">review<",
    ">approval<", ">planned<", ">competition<", ">auto<",
    ">person<", ">entrepreneur<", ">overseas<",
    ">employment_startup<", ">vocational_training<", ">hukou<", ">housing<",
    ">gba_tax<", ">inclusive_tax<", ">enterprise_support<", ">tech_enterprise<",
    ">L0<", ">L1<", ">L2<", ">L3<", ">L4<",
]
ENUM_WORDS = re.compile(
    r"\b(online|window|mixed|approval|planned|competition|review|auto|"
    r"entrepreneur|inclusive_tax|enterprise_support|tech_enterprise|"
    r"vocational_training|employment_startup|to_collect)\b"
)


# 平台风控禁用词（来自 01-C端变现计划 第 7 节）。成品里出现即需人工确认语境。
SOFT_TERMS = ["内部资料", "官方渠道", "独家", "包过", "代办", "免费领取", "一手消息", "资料包", "内部消息"]


def verify_html(html, stats):
    """交付前自检。返回问题列表（空 = 全绿）；命中禁用词的只提示不拦。"""
    problems = []
    # V1 英文枚举 / 占位符残留（只看可见文本：先去掉 style 与标签，再去掉 URL）
    body = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    body = re.sub(r"<script.*?</script>", " ", body, flags=re.S)
    visible = re.sub(r"<[^>]+>", " ", body)
    visible = re.sub(r"https?://\S+", " ", visible)
    for bad in BAD_TOKENS:
        if bad in body:
            problems.append(f"英文枚举残留 {bad}")
    for m in sorted(set(ENUM_WORDS.findall(visible))):
        problems.append(f"可见文本含英文枚举词 {m!r}")
    if re.search(r"\bNone\b|\bnull\b", visible):
        problems.append("可见文本含 None/null")

    # V2 div 配对
    if html.count("<div") != html.count("</div>"):
        problems.append(f"<div> 不配对：{html.count('<div')} vs {html.count('</div>')}")

    # V3 封面条数 = 实际条数
    m = re.search(r"<b>(\d+)</b><span>政策条目</span>", html)
    if not m:
        problems.append("封面未找到条数展示")
    elif int(m.group(1)) != stats["count"]:
        problems.append(f"封面条数 {m.group(1)} ≠ 实际 {stats['count']}")

    # V4 目录形态（2026-10-12 二次改版：多城产品目录 = 城市索引 + 类别网格）
    # 历史三代：① 初版把**每条政策**都印进目录 → 385 条占 7 页、多列容器分页留空白页；
    #          ② 改成「一行一章」的类别导航（1 页）；
    #          ③ 本版多城产品再改为「按城市查找」为**主索引** —— 读者先选城市、再选类别。
    # ⚠️ 判据一律取 **HTML 内部自洽**（目录条数 ↔ 卡片数、目录行 ↔ 正文章块），
    #    **不读外部 stats**：`tests/test_v6_dual_impl.py` 会造极简 HTML 直接调本函数，
    #    缺键会炸（2026-10-12 实测踩到：加断言后 8 条测试红）。
    cards_n = html.count('<span class="c-name">')
    toc_total = sum(int(x) for x in re.findall(r'<span class="toc-cnt">(\d+) 条</span>', html))
    if toc_total != cards_n:
        problems.append(f"目录条数合计 {toc_total} ≠ 正文卡片数 {cards_n}")
    toc_rows = html.count('<div class="toc-row">')
    # ⚠️ 用**前缀匹配**：多城产品的章是 `<section class="chap city-chap">`，
    #    写死 `class="chap">` 会数出 0（2026-10-12 实测踩到，多城两份齐齐报红）。
    chap_blocks = html.count('<section class="chap')
    if toc_rows != chap_blocks:
        problems.append(
            f"目录行数 {toc_rows} ≠ 正文章节数 {chap_blocks}"
            f"（目录须为章节导航「一行一章」，不得改回逐条罗列）")
    # 城市优先形态：目录出现「按城市查找」时，正文必须每座城市都分到类别小节。
    # 这条防的是"结构退化成半成品"：城市章建好了、章内小节没建 → 读者翻进去一片空白。
    if '<div class="idx-hd">按城市查找</div>' in html:
        sec_blocks = html.count('<div class="sec-hd">')
        if sec_blocks < toc_rows:
            problems.append(
                f"城市章内类别小节数 {sec_blocks} < 城市数 {toc_rows}"
                f"（每座城市至少要有一个类别小节，否则该城正文为空）")

    # V5 卡片完整
    cards = html.count('<div class="card">')
    names = html.count('<span class="c-name">')
    if cards != names:
        problems.append(f"卡片数 {cards} ≠ 名称数 {names}")
    if cards != stats["count"]:
        problems.append(f"卡片数 {cards} ≠ 记录数 {stats['count']}")

    # V6 每条都有可点溯源链接
    # ⚠️ 与 `verify_output.py` 的 V6 保持**同一口径**（2026-10-10 三端口径统一后补齐）：
    #    选链统一后「确无公开原文页」是**合法状态**（§5h：原文未公开则只渲染文号、留空），
    #    若继续判红，运营会集体忽略这条自检（同 §5.0b「闸门太严 → 被 --skip 绕过」）。
    #    故改为：允许 ≤5%（下限 5 条）确无原文，超出才报红（防"静默全空"没人发现）。
    #    ✅ 2026-10-12 已收口：阈值不再各写一份 —— 两处共用 `link_guard.no_orig_overflow()`。
    no_url = stats.get("no_url") or []
    # ⚠️ 上限判据真值源 = `link_guard.no_orig_overflow()`（2026-10-12 收口）。
    #    此处原为字面量 `max(5, int(stats["count"] * 0.05))` —— 与 B 端 `verify_output.py`
    #    里另写的一份实现**只靠注释保证同源**（无机器拦）。现两处共用同一函数，
    #    由 `tests/test_v6_dual_impl.py` 以 AST 断言守住。
    _over, limit = LG.no_orig_overflow(len(no_url), stats["count"])
    if _over:
        problems.append(f"缺溯源链接 {len(no_url)} 条（上限 {limit}）：{', '.join(no_url[:6])}")
    else:
        stats["no_url_legal"] = no_url

    # V7 平台禁用词扫描（提示性质，人工确认语境）
    stats["soft_hits"] = {t: visible.count(t) for t in SOFT_TERMS if t in visible}

    return problems


def html_to_pdf(html, out_pdf, workdir):
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Edge，无法转 PDF")
    os.makedirs(workdir, exist_ok=True)
    # 必须绝对路径：`file:///` + 相对路径 = 无效 URL → Chrome 报 ERR_FILE_NOT_FOUND
    # （2026-10-10 踩到：`--out` 传相对目录时整天不出 PDF，误以为是 Chrome 坏了）
    tmp_html = os.path.abspath(os.path.join(workdir, "_build.html"))
    tmp_pdf = os.path.abspath(os.path.join(workdir, "_build.pdf"))
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html)
    for p in (tmp_pdf, out_pdf):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError as e:
                raise RuntimeError(f"目标文件被占用，无法覆盖：{p}（请先关闭 PDF 阅读器）\n{e}")
    url = "file:///" + tmp_html.replace("\\", "/")
    cmd = [
        chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
        "--no-pdf-header-footer", "--virtual-time-budget=15000",
        f"--print-to-pdf={tmp_pdf}", url,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if not os.path.exists(tmp_pdf):
        raise RuntimeError(f"Chrome 转 PDF 失败\nSTDOUT:{r.stdout[-800:]}\nSTDERR:{r.stderr[-800:]}")
    shutil.move(tmp_pdf, out_pdf)
    return out_pdf


def stamp_footer(pdf_path, title, version, note):
    """逐页盖页脚（2026-10-12）。

    为什么不用 HTML 页脚：`.runfoot { position: fixed }` 在 Chrome 打印里并不驻留页脚区
    —— 实测它叠到了**页面顶部压住正文**，且负值 `bottom: -6mm` 让位置随打印边距漂移。
    改成 PDF 生成后按纸张坐标绘制：位置精确、不参与正文流、天然每页一份。

    失败不阻断出成品（页脚是装饰性信息，不是内容）：返回盖章页数，失败返回 0。
    """
    try:
        import pymupdf
    except ImportError:
        return 0
    mm = 72 / 25.4
    fs = 6.6
    margin = 13 * mm
    try:
        doc = pymupdf.open(pdf_path)
        # PyMuPDF 的内置 CJK 字体（"cjk" = Droid Sans Fallback）**不能直接当 `fontname` 用**
        # —— 会抛 `need font file or buffer`。必须取它的 buffer 显式注册进页面资源。
        font = pymupdf.Font("cjk")
        n = doc.page_count
        for i, page in enumerate(doc, 1):
            page.insert_font(fontname="FOOT", fontbuffer=font.buffer)
            w, h = page.rect.width, page.rect.height
            y = h - 9.5 * mm
            page.draw_line(pymupdf.Point(margin, y - 3.2 * mm),
                           pymupdf.Point(w - margin, y - 3.2 * mm),
                           color=(0.906, 0.933, 0.957), width=0.3)
            grey = (0.60, 0.65, 0.72)
            page.insert_text((margin, y), f"{title}　{version}",
                             fontsize=fs, fontname="FOOT", color=grey)
            right = f"第 {i} / {n} 页"
            page.insert_text((w - margin - font.text_length(right, fs), y), right,
                             fontsize=fs, fontname="FOOT", color=grey)
            page.insert_text(((w - font.text_length(note, fs)) / 2, y), note,
                             fontsize=fs, fontname="FOOT", color=(0.72, 0.76, 0.82))
        # 字体子集化：内置 CJK 字体（Droid Sans Fallback）是**整份嵌入**的（字体名无
        # `AAAAAA+` 子集前缀），25 页就多背 1.4MB。子集化后实测 2514KB → 832KB
        # （比 Chrome 原件 1131KB 还小 26%）。失败不阻断（缺 fontTools 时跳过）。
        try:
            doc.subset_fonts()
        except Exception as e:
            print(f"ℹ️ 字体子集化跳过（{type(e).__name__}: {e}）")
        # ⚠️ 不能用 `saveIncr()`：Chrome 出的 PDF 用对象流 + xref 流，增量保存会把
        #    **旧对象全部保留**（实测 1.1MB → 4.6MB，且 `/Type /Page` 能数出两倍页数）。
        #    全量重写 + 去垃圾 + 对象流压缩（`use_objstms=1`）才能把体积压回来。
        tmp = str(pdf_path) + ".stamp"
        doc.save(tmp, garbage=4, deflate=True, deflate_fonts=True,
                 use_objstms=1, clean=True)
        doc.close()
        os.replace(tmp, pdf_path)
        return n
    except Exception as e:
        print(f"⚠️ 页脚盖章跳过（{type(e).__name__}: {e}）")
        for _p in (str(pdf_path) + ".stamp",):
            if os.path.exists(_p):
                os.remove(_p)
        return 0


def write_bookmarks(pdf_path, chapters):
    """写 PDF 书签（outline）。返回写入条数，失败返回 0。

    为什么重要（2026-10-12）：此前 3 份 C 端 PDF 的书签数**都是 0** —— 电子版读者只能
    一页页翻，阅读器左侧导航栏是空的。多城读本 97~137 页，"按城市找政策"的体验又还了回去。

    定位方式：用章头 / 小节头的**编号区间串**做锚点（形如「编号 064–095」）。
    这个串在全文唯一 —— 目录里的区间**不带「编号」二字**（`toc-range`）、卡片上只有单个
    编号，所以首次命中即正文该章所在页，不依赖任何页序假设。
    ⚠️ 若日后改动章头措辞（去掉「编号」前缀），书签会**静默失锚**（返回条数变少但不出错），
    故 `tests/test_pdf_layout.py` 以「多城产品书签数 ≥ 城市数 + 小节数」反向锁住。
    """
    try:
        import pymupdf
    except ImportError:
        return 0

    def _norm(s):
        s = re.sub(r"\s+", "", s or "")
        return re.sub(r"[\u2010-\u2015\u2212]", "-", s)

    def _find(pages, anchor):
        a = _norm(anchor)
        if not a:
            return None
        for i, t in enumerate(pages):
            if a in t:
                return i + 1
        return None

    try:
        doc = pymupdf.open(pdf_path)
        pages = [_norm(p.get_text()) for p in doc]
        toc = []
        for ch in chapters:
            if not ch.get("no_from"):
                continue
            pg = _find(pages, f"编号{ch['no_from']}-{ch['no_to']}")
            if pg is None:
                continue
            toc.append([1, ch["name"], pg])
            for s in (ch.get("sections") or []):
                if not s.get("no_from"):
                    continue
                sp = _find(pages, f"编号{s['no_from']}-{s['no_to']}")
                if sp is not None:
                    toc.append([2, s["name"], sp])
        if not toc:
            doc.close()
            return 0
        doc.set_toc(toc)
        tmp = str(pdf_path) + ".bmk"
        doc.save(tmp, garbage=4, deflate=True, deflate_fonts=True,
                 use_objstms=1, clean=True)
        doc.close()
        os.replace(tmp, pdf_path)
        return len(toc)
    except Exception as e:
        print(f"⚠️ 书签写入跳过（{type(e).__name__}: {e}）")
        _p = str(pdf_path) + ".bmk"
        if os.path.exists(_p):
            os.remove(_p)
        return 0


def count_pages(pdf):
    """页数。

    ⚠️ 2026-10-12：原先用正则数 `/Type /Page` —— 只要 PDF 被增量保存过（旧对象残留）
    就会数出**两倍的页数**（盖章后 25 页被读成 50 页）。改用 PyMuPDF 读页树。
    """
    try:
        import pymupdf
        doc = pymupdf.open(pdf)
        n = doc.page_count
        doc.close()
        return n
    except ImportError:
        with open(pdf, "rb") as f:
            b = f.read()
        return len(re.findall(rb"/Type\s*/Page[^s]", b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=list(PRODUCTS),
                    help="多城 / 全量产品：%s" % " / ".join(PRODUCTS))
    ap.add_argument("--city", metavar="城市码",
                    help="单城产品：出「{城市}个人补贴清单」，如 SZ / GZ / SU。"
                         "可单独成册的城市由 release_matrix.city_pdf_jobs() 现算")
    ap.add_argument("--src", default=loader.DEFAULT_SRC)
    ap.add_argument("--out", default=os.path.join(ROOT, "output", "C端"))
    ap.add_argument("--link-strict", action="store_true",
                    help="L5：连栏目/聚合页、政策解读页、新闻页也降级（默认只降死链+明文文种错）")
    a = ap.parse_args()

    global LINK_STRICT
    LINK_STRICT = a.link_strict

    if bool(a.preset) == bool(a.city):
        ap.error("必须且只能指定一个：--preset（多城 / 全量）或 --city（单城城市码）")
    try:
        prod = resolve_preset(CITY_PREFIX + a.city) if a.city else PRODUCTS[a.preset]
    except KeyError as e:
        ap.error(str(e))
    _all = loader.load_all(a.src)
    rows = loader.filter_cities(_all, prod["cities"])

    # 成品层收录口径（2026-10-10）：**只接入现行有效政策**。
    # 非现役（exited/renamed/merged/superseded）仍留在库、前端仍以「备查」区块展示，
    # 但不进这本读本 —— C 端读者是普通个人，把已下线政策印进"你能申报的清单"
    # 只会让他白跑一趟（比 B 端更不可接受）。
    _n_city = len(rows)
    rows = loader.filter_active(rows)
    _n_dropped = _n_city - len(rows)
    # 全库现行有效 —— 「适用范围」层级判定的基准（判国家级 vs 省级必须跳出本表，见 cross_city docstring）
    _active_all = loader.filter_active(_all)

    # 省表产品（province 非空）：跨城归并 + 覆盖率标注。
    # 判据与 B 端 export_excel 同源（`cross_city.py` / `geo.py`），不各写一份。
    _merge_stat, _cov = None, None
    if prod.get("province"):
        rows, _merge_stat = cross_city.merge(
            rows, province=prod["province"], all_rows=_active_all)
        _cov = geo.coverage(prod["province"], prod["cities"])
        prod = dict(prod)                      # 浅拷贝，不改 PRODUCTS 常量
        prod["merge_note"] = (
            f"省级与国家级政策已合并去重（原按各市重复列出）；本次合并 "
            f"{_merge_stat['groups']} 组、去重 {_merge_stat['dropped']} 条重复条目，"
            f"并逐条标注适用范围 —— 省级政策标注「{prod['province']}全省」、国家级政策标注「全国通用」。")
        if _cov["total"]:
            _miss = (f"，另 {len(_cov['missing_names'])} 个地级市尚未收录"
                     if _cov["missing_names"] else "")
            prod["scope"] = (f"{prod['province']}（已收录 {len(_cov['covered'])}/{_cov['total']} "
                             f"个地级市：{'、'.join(_cov['covered_names'])}{_miss}）")

    # 多区域产品（无省份、cities=None）：覆盖清单**从数据现算** —— 见 coverage_scope_text 的
    # 事故说明（写死清单 → 新增城市后产品名/封面失真）。
    if not prod.get("province") and not prod.get("cities"):
        prod = dict(prod)                      # 浅拷贝，不改 PRODUCTS 常量
        prod["scope"] = coverage_scope_text(rows)

    html, stats = build_html(rows, prod, a.src, all_rows=_active_all)
    if not stats.get("count"):
        # 防"静默出空册子"：城市码打错 / 该城全是企业专项 / 政策全部下线 —— 都要拦住，
        # 否则会产出一本只有封面和免责页的 PDF 被当成成品交付。
        print("❌ 最终收录 0 条 —— 不出空册子。"
              "请检查：城市码是否正确 / 该城是否有 C 端可申报的**现行有效**政策")
        return 3
    problems = verify_html(html, stats)

    print(f"=== {prod['title']} ===")
    print(f"源读取：{_n_city} 条 → 现行有效 {len(rows)} 条（过滤非现役 {_n_dropped} 条）"
          f" → C 端收录（{PERSON_SCOPE_SLASH}）：{stats['count']} 条")
    if _merge_stat:
        print(f"🔀 跨城归并 {_merge_stat['groups']} 组、去重 {_merge_stat['dropped']} 条"
              f"（省级→「{prod['province']}全省」、国家级→「全国」）")
    if _cov and _cov["total"]:
        print(f"📍 覆盖 {prod['province']} {len(_cov['covered'])}/{_cov['total']} 个地级市"
              f"，未覆盖 {len(_cov['missing_names'])} 个（已写入封面口径）")
    if stats["multi_city"]:
        print(f"分章：{stats['chapters']} 座城市 × {stats['sections']} 个类别小节  " +
              " ｜ ".join(f"{c['name']} {c['count']}" for c in stats["chapters_meta"]))
    else:
        print(f"分章：{stats['chapters']} 类  " +
              " ｜ ".join(f"{k} {v}" for k, v in stats["by_domain"].items()))
    print()
    if problems:
        print("❌ 交付前自检未通过：")
        for p in problems:
            print("   -", p)
    else:
        print("✅ 交付前自检通过（V1 无残留 / V2 div 配对 / V3 封面条数 / V4 目录条数 / V5 卡片完整 / V6 溯源链接）")
    legal = stats.get("no_url_legal") or []
    if legal:
        print(f"ℹ️ 其中 {len(legal)} 条确无公开原文页（只渲染文号，§5h 合法状态）："
              f"{', '.join(legal[:6])}")
    hits = stats.get("soft_hits") or {}
    if hits:
        print("⚠️ 平台禁用词命中（需人工确认语境，反向警示语可接受）：" +
              " ｜ ".join(f"{k}×{v}" for k, v in hits.items()))

    os.makedirs(a.out, exist_ok=True)
    workdir = os.path.join(a.out, "_build")
    pdf_path = os.path.join(a.out, f"{prod['fname']}_{VERSION}.pdf")
    html_path = os.path.join(a.out, f"{prod['fname']}_{VERSION}.html")

    try:
        pdf = html_to_pdf(html, pdf_path, workdir)
    except RuntimeError as e:
        print(f"❌ {e}")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"   HTML 已保留供排查：{os.path.relpath(html_path, ROOT)}")
        return 2

    # ⚠️ 盖章必须排在**写 HTML 之前**：既有约定是 `main()` 先出 PDF、后落 HTML
    #    （见技能 §10「html.mtime > pdf.mtime 正常」），盖章会重写 PDF 从而更新其 mtime，
    #    排在 HTML 之后会把这条时序约定反过来，可能让成品时效断言误判。
    _stamped = stamp_footer(pdf_path, prod["title"], VERSION, FOOTER_NOTE)
    if _stamped:
        print(f"🖨 页脚逐页盖章 {_stamped} 页（产品名 · 版本 · 页码 · 合规口径）")

    # 书签同样必须排在写 HTML 之前（它会重写 PDF 从而更新 mtime，理由见上）。
    _bmk = write_bookmarks(pdf_path, stats["chapters_meta"])
    if _bmk:
        _kind = "城市 → 类别小节" if stats["multi_city"] else "类别"
        print(f"🔖 PDF 书签 {_bmk} 条（{_kind}），电子版可直接跳转")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    pages = count_pages(pdf)
    size = os.path.getsize(pdf) / 1024
    print()
    if DOWNGRADED:
        _dp = os.path.join(os.path.dirname(pdf),
                           "_link_degrade_%s.md" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
        _lines = ["# C 端出成品链接降级台账（L5）", "",
                  "> 成品：`%s`" % os.path.basename(pdf),
                  "> 规则：`pipeline/link_guard.py`｜判据源：源库 `policy_hub/collector/link_audit.json`",
                  "> 含义：下列链接**未渲染进成品**（读者看不到超链接），只留文号，避免点到坏链/错页。", ""]
        _lines += ["- `%s` ｜ %s ｜ %s" % (i, why, u) for i, why, u in DOWNGRADED]
        open(_dp, "w", encoding="utf-8").write("\n".join(_lines))
        print("🔗 链接降级 %d 处（读者不会点到坏链）→ %s" % (len(DOWNGRADED), _dp))

    print(f"✅ 已生成：{os.path.relpath(pdf, ROOT)}")
    print(f"   页数 {pages} ｜ 条目 {stats['count']} ｜ {size:.0f} KB")
    print()
    print(M.report_unmapped())
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
