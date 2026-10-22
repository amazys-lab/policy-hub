# -*- coding: utf-8 -*-
"""
字段映射与中文化 · 成品校验第一关
--------------------------------------------------
规则：源数据保持英文枚举，成品一律中文。
     映射表里没有的值 → 记入 UNMAPPED 并显式暴露，绝不静默输出英文。
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, "enum_map.json"), encoding="utf-8") as f:
    MAP = json.load(f)

# 导出过程中发现的所有未映射值：{字段: {原值: 出现次数}}
UNMAPPED = {}


# 文件已届满的执行状态（2026-10-18）。命中这些值 ⇒「有效期」列必须同时印出 exec_note，
# 不许只印 `有效期至 <日期>` —— 否则客户把「文件届满」误读成「政策失效」。
EXEC_EXPIRED_STATUS = ("expired_continuing", "pending_renewal", "expired_stopped")


def _s(v):
    """None 安全的字符串化：None → 空串。

    ⚠️ 为什么必须有这个函数（2026-10-09 实锤）：字段统一批把 `deadline.expire/cycle/mode`、
    `apply_window.batch` 等改成了**显式 null**（全库 expire null 429 条 / cycle 183 / mode 124）。
    而旧代码到处写 `str(x.get(k, ""))` —— 键存在、值是 None 时 `str(None)` 得到字面量
    `"None"`，直接印进客户可见单元格（实测成品 V2 校验 110 处占位符残留）。
    旧代码在 `_clean_date` 里手工塞了一个 `"None"` 哨兵，但只补了那一处 —— 典型的
    「修一个冒一个」。故统一收口到本函数：**任何要变成人读文本的值，都必须先过 `_s()`**。
    """
    return "" if v is None else str(v).strip()


def t(field, value):
    """把某个字段的枚举值翻成中文；空值返回空串。"""
    if value is None or value == "":
        return ""
    s = str(value)
    table = MAP.get(field, {})
    if s in table:
        return table[s]
    UNMAPPED.setdefault(field, {})
    UNMAPPED[field][s] = UNMAPPED[field].get(s, 0) + 1
    return s  # 原样返回，由导出器汇总报警


def city(code):
    return t("city", code)


def province(code):
    return MAP.get("province", {}).get(str(code).upper(), "")


def domain_short(value):
    """业务域 → **紧凑位**短名（目录速览 / 章头速览 / 人读清单用）。

    ★ 为什么单独一张表而不是从全名截断（2026-10-17 C 项）：
      紧凑位要在**一行**里放下 5~7 个类别，「大湾区个税补贴」这类全名会撑爆行宽，
      而「就业创业补贴」→「就业创业」这种缩写**不可计算**。故短名是独立数据，
      但必须与全名同处**同一份真值源**（`enum_map.json`），三表键集完全相等。
      `tests/test_domain_labels.py::DL1/DL2` 守这一点。
    未登记的域 ⇒ 回退全名（`t("domain")`），再退原值 —— 绝不吐空串。
    """
    s = _s(value)
    if not s:
        return ""
    return MAP.get("domain_short", {}).get(s) or t("domain", s) or s


def domain_desc(value):
    """业务域 → 人读**描述句**（成品域章导语 / 前端卡片副标题）。

    与全名同源（`enum_map.json::domain_desc`），不再各端各写一份。
    未登记 ⇒ 空串（描述句缺失是**可空**的，不得用印象文案补齐 —— §5b 禁止静默降级）。
    """
    s = _s(value)
    return MAP.get("domain_desc", {}).get(s, "") if s else ""


def applicant_kinds(cond):
    """cond.applicant_kinds -> 「个人 / 用人单位」"""
    if not isinstance(cond, dict):
        return ""
    ks = cond.get("applicant_kinds") or []
    return " / ".join(t("applicant_kind", k) for k in ks)


def amount_text(rec):
    """金额列：优先取 text（人读完整表述），退化为按 kind 拼装。"""
    a = rec.get("amount")
    if not isinstance(a, dict):
        # 资格通道 / 评审认定类本就无现金补贴，填明确文案而非留空
        rt = _s(rec.get("result_type"))
        if rt in ("channel", "review") or not a:
            return "非现金项目：资格通道 / 评审认定，无补贴金额"
        return ""
    if _s(a.get("text")):
        return _s(a["text"])
    k = a.get("kind", "")
    label = t("amount_kind", k)
    unit = _s(a.get("unit"))
    if k == "once":
        return f"{_s(a.get('value'))}{unit}，{label}"
    if k in ("month_x_count", "once_x_count", "per_year_x_count"):
        return f"{_s(a.get('per'))}{unit or '元/人'}，{label}"
    if k == "range":
        return f"{_s(a.get('min'))}-{_s(a.get('max'))}{unit}，{label}"
    if k == "percent_of_base":
        return f"按基数 {_s(a.get('ratio'))} 比例返还，{label}"
    if k == "tiered_hire":
        return (f"首 {_s(a.get('first_n'))} 人每人 {_s(a.get('first'))} 元，"
                f"其后每人 {_s(a.get('rest'))} 元，上限 {_s(a.get('cap'))} 元")
    return label


def amount_low_high(rec):
    """返回 (下限, 上限) 数值元组，用于排序与筛选；无法定量返回 (None, None)。"""
    a = rec.get("amount")
    if not isinstance(a, dict):
        return None, None
    k, v = a.get("kind"), a.get("value")
    if k == "once":
        return v, v
    if k == "range":
        return a.get("min"), a.get("max")
    if k in ("month_x_count", "once_x_count", "per_year_x_count"):
        return a.get("per"), a.get("per")
    if k == "tiered_hire":
        return a.get("first"), a.get("cap")
    return None, None


# 子项值自带标签时的去重判据（2026-10-10 实测出的数据形态）：
# 存量 15 子项的 first/renew 值**形态不统一** —— 多数是纯标准（"一次性20万元"），
# 少数已自带标签（"首次认定:…8万元"、"重新认定2万元"）。
# 渲染层若一律加前缀，就会产出「重新认定 重新认定2万元」。**不改数据**（改值属事实层，
# 且这些标签本身没错），而是给渲染层一条**明确规则**（非猜测）：值以同义标签开头则不再加前缀。
_LABEL_SYN = {
    "first": ("首次", "第一次", "首认", "通过认定", "初次"),
    "renew": ("重新", "非首次", "再次", "复审", "延续", "二次"),
}


def _with_label(label, v, key):
    """按需加前缀：值已自带同义标签 → 原样用，避免「重新认定 重新认定2万元」。"""
    s = _s(v)
    if not s:
        return ""
    if s.startswith(_LABEL_SYN.get(key, ())):
        return s
    return label + s


def district_awards_text(rec, sep="\n", action_sep="；"):
    """区县/镇街配套对照（2026-10-10 字段转正，由幽灵字段升为契约字段）。

    背景：该字段此前「无契约、无闸门、无渲染」三无，内部字段名还被写进了客户可见的
    `amount.text`（悬空指引）。转正方案见 `contract.md §5.1` / `schema.district_awards_fields`，
    闸门第 25 项校验结构。**与 `amount` 的分工**：`amount` = 市级/本级统一标准；
    本字段 = 下辖各区县/镇街对**同一事项**的差异化部分，两者不重复叙述。

    输出形态（每条一行，按数组原序 —— 原序即采集时的官方/行政排序，**勿重排**）：
        `某某区：首次认定 20万元；重新认定 10万元（依据：《某某区若干措施》第二条）`

    ★ 只渲染**有内容的子项**：整字段空/缺/null → 返回 `""`（列留空，不写"无"占位，
      否则大量没有该字段的记录会被塞满噪音 —— 同 `_s()` 一节的教训）。
    ★ `url` 刻意**不进文本**：B 端一格只能挂一个超链接，塞多链会自相矛盾；
      前端另有链接渲染（读 `it["url"]`），两端口径分工见 contract.md §5.1 `_渲染`。
    """
    da = rec.get("district_awards")
    if not isinstance(da, list):
        return ""
    lines = []
    for it in da:
        if not isinstance(it, dict):
            continue
        name = _s(it.get("district"))
        if not name:
            continue
        parts = []
        first = _with_label("首次认定 ", it.get("first"), "first")
        if first:
            parts.append(first)
        renew = _with_label("重新认定 ", it.get("renew"), "renew")
        if renew:
            parts.append(renew)
        move_in = _s(it.get("move_in"))
        if move_in:
            parts.append(move_in)
        line = name + "：" + action_sep.join(parts) if parts else name + "："
        note = _s(it.get("note"))
        if note:
            line += "（注：" + note + "）"
        basis = _s(it.get("basis"))
        if basis:
            line += "（依据：" + basis + "）"
        lines.append(line)
    return sep.join(lines)


def apply_window_text(rec):
    """申报窗口：batch + note；to_collect 一律转成「以当年通知为准」。"""
    aw = rec.get("apply_window")
    if not isinstance(aw, dict):
        return ""
    batch = _s(aw.get("batch"))
    note = _s(aw.get("note"))
    batch = "以当年官方通知为准" if batch in ("to_collect", "") else batch
    if note and note != batch:
        return f"{batch}；{note}"
    return batch


def _clean_date(v):
    s = _s(v)
    if s in ("to_collect", "", "None"):
        return "以当年通知为准"
    return s


def deadline_text(rec):
    """有效期：优先 expire，退化到 text/cycle；兼容 deadline 为字符串的写法。"""
    dl = rec.get("deadline")
    if isinstance(dl, str):
        return dl.strip() or "长期有效，以当年官方通知为准"
    if not isinstance(dl, dict):
        return "长期有效，以当年官方通知为准"
    exp = _clean_date(dl.get("expire"))
    if re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", exp):
        # ★ 2026-10-18 修 bug：「有效期」列曾只印 `有效期至 2024-12-31` 就 return，
        #   把 exec_note 里「文件已届满但仍在拨付」整段解释**遮掉** ⇒ 客户误判失效、放弃申请。
        #   这不是排版问题：同一条记录的 `amount`/`notes` 都在说「还在执行」，只有这一列唱反调。
        #   修法：只要标了 exec_status（文件届满类），日期后面必须把执行状态和人读说明一起印出来。
        es = _s(dl.get("exec_status"))
        if es in EXEC_EXPIRED_STATUS:
            note = _s(dl.get("exec_note"))
            base = f"有效期至 {exp}"
            if note:
                return f"{base}；{note}"
            return f"{base}（{t('exec_status', es)}）"   # 兜底：至少是中文标签，绝不印英文枚举
        return f"有效期至 {exp}"          # 规范日期才加前缀
    if exp and exp != "以当年通知为准":
        return exp                        # expire 里写的是文字说明，原样用
    # ⚠️ 2026-10-10 修 bug：原退化链是 `cycle → mode → text`，而 `mode` 是**英文枚举**
    #    （rolling / fixed / annual / once）—— `cycle` 为空时就直接把 `'rolling'` 印进
    #    客户可见的「有效期」列（全库实测 **86 条**，V1–V7 未拦）。这 86 条其实**都有 `text`**
    #    （人读完整说明，如「毕业2年择业期内均可申办，无固定申报截止日…」），只是被 mode 挡住了。
    #    修法两条：① 把 `text` 提到 `mode` 之前（人读长句信息量更大）；
    #              ② `mode` 必须经 `t("deadline_mode", …)` 中文化（即便将来 text 也空，
    #                 落到的也是中文兜底文案，绝不会再印英文枚举）。
    for k in ("cycle", "text"):
        v = _s(dl.get(k))
        if v:
            return v
    mv = _s(dl.get("mode"))
    if mv:
        return t("deadline_mode", mv)
    return exp if exp else "长期有效，以当年官方通知为准"


# ── 申报条件：cond 的 7 类载体 → 人读条目 ────────────────────────────
# ★ 2026-10-12 修复（起因：用户质询「申报条件为什么会有空白，政策原文不是都有的吗」）。
#   旧实现只读 `cond.must`，而库里条件实际落在 **6 处**：
#     must          硬性条件（逐条 AND）
#     base_must     基础条件（与 must 同构；分支型政策把公共条件放这里）
#     branches[]    择一分支（**组内 AND、组间 OR**，形如「学历-本科以上45岁以下」+ 条件）
#     any_must      {"label":…, "conds":[…]} —— 组内 OR，整体与 must 是 AND
#     manual_check  一整句人读条件（条件落不到前端字段时采集侧写这里）
#     score_rule / points_cutoff  积分规则与入围线
#   实测成品「申报条件」列 B 端空 193/806、C 端空 128/385，其中 **175 条信息本来就在库里**
#   —— 抓原文比对（南京《高校毕业生生活补贴操作办法》「第三章 申请条件和时限 第四条」）
#   确认原文均有条件 ⇒ **渲染缺陷，不是数据缺陷**。旧版还因此把 18 条真缺口误写成
#   「原文未列明」（实为采集漏抽），见报告 `61-`。
#   ⚠️ 本函数是**唯一实现**：`conditions_text()` 与 `export_pdf._conditions_line()` 都从它取条目。
#      旧版两处各写一份（都只读 must），漏读集合完全一致却要改两处 —— 判据分叉。
_ANY_PREFIX = "满足以下任一类即可："


def _cond_label(m):
    """单个条件元素 → 人读文本：dict 取 label，字符串原样，其它忽略。"""
    if isinstance(m, dict):
        return _s(m.get("label"))
    return _s(m)


def condition_items(rec):
    """把 `cond` 各载体统一抽成**人读条件条目**（有序，按读起来最顺）。

    ⚠️ 不渲染 `any_identities`：实测 743 条有值、其中 **0 条单独承载条件**
       （全部与 must / base_must / branches / manual_check 等载体并存）——
       渲染它只会与既有条目**重复**，把「申报条件」变成一个更长的同义列表。
       中文映射已**补全**到 `enum_map.json["identity"]`（22/22，2026-10-13），
       所以「展开会印英文枚举」的风险已消除；不渲染是**信息去重**的选择，不是缺表。
       若将来出现「只靠 any_identities 承载条件」的记录，`test_condition_render.py` 会报红。
    """
    cd = rec.get("cond")
    if not isinstance(cd, dict):
        return []
    out = []

    # 1) manual_check：人读条件。**两种形态都必须支持**（2026-10-17 实锤缺陷）：
    #    · 字符串（schema 声明形态）= 一整句人读条件
    #    · 字符串数组（HG 回补 / CD 补域两批新采在用）=「一条 = 一个条件条目」，语义更细
    #    ★ 若只做 `_s()` 收口，数组会退化成 Python 列表字面量 `['…','…']`（含方括号与直角引号）
    #      印进客户可见的「申报条件」单元格 / C 端 PDF —— 与 `str(None)` 同族的占位符缺陷，
    #      且实测已在杭州 v20261016 成品出货（HG-HS-001~003 / OS-HG-001~003 共 6 条）。
    #    ★ 数组形态顺带修正 `conditions_text(limit)` 的计数：字符串形态整句只算 1 条，
    #      数组形态按条计数 ⇒ 截断行为与「另有 N 项」提示才是准的。
    mc = cd.get("manual_check")
    if isinstance(mc, (list, tuple)):
        out += [x for x in (_s(i) for i in mc) if x]
    elif _s(mc):
        out.append(_s(mc))

    # 2) must / base_must：同构，逐个 label
    for key in ("must", "base_must"):
        for m in (cd.get(key) or []):
            lb = _cond_label(m)
            if lb:
                out.append(lb)

    # 3) any_must：组内 OR（整体与 must 是 AND），有整体 label 时优先用它
    am = cd.get("any_must")
    if isinstance(am, dict):
        lb = _s(am.get("label"))
        subs = [x for x in (_cond_label(c) for c in (am.get("conds") or [])) if x]
        if lb:
            out.append(_ANY_PREFIX + lb)
        elif subs:
            out.append(_ANY_PREFIX + "／".join(subs))
    elif isinstance(am, list):          # 历史扁平形态（当前库内 0 条，兼容保留）
        subs = [x for x in (_cond_label(c) for c in am) if x]
        if subs:
            out.append(_ANY_PREFIX + "／".join(subs))

    # 4) branches：**组间 OR、组内 AND** —— 必须标出「任一类」，否则会被读成「全都要」
    brs = []
    for b in (cd.get("branches") or []):
        if not isinstance(b, dict):
            continue
        ms = [x for x in (_cond_label(c) for c in (b.get("must") or [])) if x]
        if not ms:
            continue
        nm = _s(b.get("name"))
        brs.append((nm + "：" if nm else "") + "、".join(ms))
    if brs:
        out.append(_ANY_PREFIX + "；".join(brs))

    # 5) 积分类：公式说明与入围线
    sr = cd.get("score_rule")
    if isinstance(sr, dict):
        note = _s(sr.get("formula_note"))
        if note:
            out.append(note)
    pc = cd.get("points_cutoff")
    if pc not in (None, "", [], {}):
        out.append("积分入围线 %s 分" % _s(pc))

    return out


def conditions_text(rec, limit=6):
    """申报条件（Excel 单元格用）：`condition_items` 的分号串，超限截断并明示还有几项。"""
    items = condition_items(rec)
    more = ""
    if len(items) > limit:
        more = f"（另有 {len(items) - limit} 项，见原文）"
        items = items[:limit]
    return "；".join(items) + more


def materials_text(rec, limit=8):
    ms = rec.get("materials")
    if not isinstance(ms, list):
        return ""
    ms = [_s(x) for x in ms]
    ms = [x for x in ms if x]
    more = ""
    if len(ms) > limit:
        more = f"（共 {len(ms)} 项）"
        ms = ms[:limit]
    return "\n".join(f"{i+1}. {x}" for i, x in enumerate(ms)) + more


def entry_url(rec, audit=None):
    """「办理入口」链接：**只认 `apply_url`**；无则返回空串（如实留空）。

    ★ 2026-10-17 取消回退链（原链：`apply_url` -> `guide_url` -> **合格的** `sources`）。
      取消理由（事故原型见 `86-` 报告 §2）：
      · 「-> `guide_url`」这一跳是**无条件**的，但它声称服务的场景
        （「原文与入口同页」）在库里**不存在** —— 全库实测 `apply_url == guide_url`
        的同页记录 **0 条**。==> 它从未服务设计意图，只在**制造假入口**：
        凡 `apply_url` 空、`guide_url` 合格的记录，成品「办理入口」必然被印成
        政策原文页 —— 客户点开期待申报页、拿到的是政策文件
        （同 `OS-HP-201`「办理入口 = 新闻页」一族）。
      · 连带把 `verify_output` 的 V7「溯源独立率」污染成「有多少条政策没有线上入口」
        （B 端报 117 条、C 端某城 25% 判红），而源库同页实为 0 ==> 测量面错层。
      · 口径铁律：**禁止静默降级** —— 缺数据就留空，不得用别的东西顶替。

    ★ 「空」是合法状态，且源库已如实记录：全库 `apply_url` 空 118 条
      （按 `channel` 拆：`window` 32 仅线下 / `mixed` 64 线上线下均可 / `online` 21，
       其中 21 条里 12 条入口在 APP、小程序、公众号或邮箱，客观没有网页 URL）。
      客户靠**字段说明**（「留空 = 该政策无统一在线申报页面」）与「办理渠道」列
      得知怎么办 —— 不靠硬塞链接，那正是 `OS-HP-201` 的推手。
    ★ 防「静默全空」改由 `verify_output` V6 的**对账**兜住
      （`link_guard.entry_reconcile`：成品空条数必须 == 源库 `apply_url` 空条数）。

    `audit` 参数保留仅为**调用方兼容**（回退链取消后本函数不再需要基线）。
    """
    v = _s(rec.get("apply_url"))
    return v if v.startswith("http") else ""


def channel_note(rec):
    """「渠道说明」真值：`channel_detail` → `where`（办理地点）。**三端必须同源**。

    ★ 2026-10-14 统一（事故原型）：此前 **B 端 Excel 只取 `channel_detail`**
      （实测 62 条空入口里 41 条因此无任何文字说明），而 **C 端 PDF 取
      `channel_detail or where`** ⇒ 同一条政策在两份成品里说法不同。
      真值源收口到此函数；各端只在自己那层做**截断/清洗**（PDF 有排版宽度约束）。
    """
    return _s(rec.get("channel_detail")) or _s(rec.get("where"))


_URL_RE = re.compile(r"https?://[^\s，,；;、）)\]}】\"']+")
# 像「政策原文/规范性文件」的路径特征（政府站点的政策法规库、公开目录、附件）
_POLICY_PATH = re.compile(
    r"/zcfg|/zcwj|/gkmlpt|/zwgk|/zfxxgk|/xxgk/|/zhengce|/fg/|/fgk/|/zfwj|\.pdf$|\.docx?$",
    re.I,
)


def _urls_of(rec):
    """收集该条记录可作选链候选的 URL —— **只取 `sources` 列表**，去重保序。

    ⚠️ 2026-10-10 职责分离（改前还从 `source_doc` 抽 URL）。那让一个**人读**字段
    （文号 + 出处）同时当了**机器选链的候选池**：采集时顺手把原文页 URL 抄进
    `source_doc`，选链就会把它当候选 —— 同一份数据在不同出口得出不同结果，根因即此
    （见技能 §6.28/§6.29）。现判据：
      · 机器选链**只用结构化字段** `guide_url` / `sources`；
      · `source_doc` 只作人读依据，闸门第 21 项**禁止**其内嵌 URL。
    """
    out = []
    for u in (rec.get("sources") or []):
        if isinstance(u, str) and u.startswith("http"):
            out.append(u.strip())
    seen, res = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            res.append(u)
    return res


_AUDIT_CACHE = None


def _get_audit():
    """延迟加载链接判据（缓存）。真值源唯一 = link_guard.load_audit()。"""
    global _AUDIT_CACHE
    if _AUDIT_CACHE is None:
        try:
            import link_guard as _LG
            _AUDIT_CACHE = _LG.load_audit()
        except Exception:
            _AUDIT_CACHE = {}
    return _AUDIT_CACHE


def reset_audit_cache():
    """测试 / 基线更新后重载用。"""
    global _AUDIT_CACHE
    _AUDIT_CACHE = None


def original_doc_url(rec, audit=None):
    """政策原文链接 —— **三端口径统一**（2026-10-10 起）。

    改前问题（存量治理发现）：本函数按「路径像不像政策原文」挑链，把 `sources` 排在
    `guide_url` 前面且**不做质量校验** → 客户在 B端 Excel/C端 PDF 里点「政策原文」
    被喂到 404 / 问答页 / 公示页 / 办事指南页；而前端网页读的是 `guide_url`，看到的
    反而是对的 —— 同一份数据，三个出口三种结果。

    新口径（与前端渲染的 `guide_url` 对齐）：
      1) `guide_url` 若是「可作政策原文的文种」→ 直接用它
         （判据 = `link_guard.guide_slot_ok`：非坏链 + 非办事入口形态 + 文种属原文类）
      2) 否则在 `source_doc` / `sources` 里挑**合格**候选，按文种分三层：
           tier 1  HTML 原文类（原文页 / 政策清单页）  ← 首选，可读可核验
           tier 2  PDF附件原文                        ← 兜底（附件可能是名单/表格/扫描件）
           tier 3  未归类                             ← 缺证据不动手（与"不降级"原则一致）
         每层内部再沿用原 A/B/C 分层：
           A 非办理入口 且 路径像政策原文（/zcfg /gkmlpt /zwgk /xxgk .pdf ...）
           B 非办理入口
           C 与办理入口同页（原文与办事入口同页，属可接受的兜底）
      3) 全不合格 → 返回 ""（成品只渲染文号，不给坏链；见技能 §5h「原文未公开则留空」）

    ⚠️ R1 的实测依据（为什么 HTML 优先于 PDF）：同一记录里既有 HTML 原文页又有 PDF 附件时，
       附件常常不是原文 —— 有的 PDF 其实是「符合发放条件名单公示」，有的
       是 4 页无文本层扫描件。附件文种无法靠路径判断，故让 HTML 原文页先选。

    参数 `audit` 为链接判据真值源（`policy_hub/collector/link_audit.json`）；
    省略时自加载并缓存，保证与导出器/校验器读的是同一份判据。
    """
    import link_guard as _LG
    aud = _get_audit() if audit is None else audit

    gu = _s(rec.get("guide_url"))
    if _LG.guide_slot_ok(gu, aud):
        return gu

    cands = [u for u in _urls_of(rec) if _LG.guide_slot_ok(u, aud)]
    if not cands:
        return ""
    excl = {_s(rec.get(k)) for k in ("apply_url", "guide_url")}
    excl.discard("")
    tiers = ([u for u in cands if _LG.cls_of(u, aud) in _LG.HTML_GUIDE_KINDS],
             [u for u in cands if _LG.cls_of(u, aud) in _LG.ATTACH_GUIDE_KINDS],
             [u for u in cands if _LG.cls_of(u, aud) not in
              _LG.HTML_GUIDE_KINDS | _LG.ATTACH_GUIDE_KINDS])
    for pool in tiers:
        if not pool:
            continue
        for sub in ([u for u in pool if u not in excl and _POLICY_PATH.search(u)],
                    [u for u in pool if u not in excl],
                    [u for u in pool if u in excl]):
            if sub:
                return sub[0]
    return ""


def source_ref_count(rec):
    """该条可溯源链接总数（去重后），用于判断溯源强度。"""
    return len(_urls_of(rec))


DOC_NO = re.compile(r"[\u4e00-\u9fa5]{2,12}[〔\[（]\d{4}[〕\]）]\s*(?:第)?\s*\d+\s*号")

# ── 客户可见「政策依据」文本的呈现规则（2026-10-10） ───────────────────────
# 1) 口径句前置：防客户「把省级政策误认成本市政策」——这是实质口径误导，不是排版问题
# 2) 截断上限抬到 300：全库实测最长 290 字（逐区罗列 11 个区级办法的情形），
#    120 字会切掉多依据清单的后半截 → 改 300 = 事实上的不截断（保留作未来防爆阈值）
SOURCE_DOC_MAX = 300

# 口径/免责说明句的识别核心：凡「本级未检索到 / 未公开 / 未单列原文」或
# 「申报口径以（本级）为准 / 执行口径见」都属同簇 —— 客户必须看到。
_NOTE_CORE = (r"(?:未检索到|暂无[^，。；]{0,10}原文页|未单列|未公开|未列入"
              r"|口径以[^，。；]{0,12}为(?:准|依据)|执行口径见)")
POLICY_NOTE_PAT = re.compile(_NOTE_CORE)
_CAUSAL_LEAD = re.compile(r"(?:因|由于|鉴于)")     # 因果连词：其前是文号/标题
_BRACKET_OPEN, _BRACKET_CLOSE = "（(《【", "）)》】"


def _split_sents(s):
    """按「；;。」分句，但**跳过括号内**的分隔符；「，」仅在其后紧跟口径句时才算边界。

    若不配平括号，`《…》（…发布；该文件未列入…为准）：内容` 会被从括号内的 `；`
    切开 → 前置后左括号悬空（实测踩到）。故按括号深度只在最外层切。
    半角「，」密度高、不能通吃，只对「，上一级执行口径见…」这类**逗号后紧跟口径句**
    的形态开边界（实测踩到：全句只有逗号，不切就永远前置不了）。
    """
    out, buf, depth = [], [], 0
    for i, ch in enumerate(s):
        buf.append(ch)
        if ch in _BRACKET_OPEN:
            depth += 1
        elif ch in _BRACKET_CLOSE:
            depth = max(0, depth - 1)
        elif depth == 0 and ch in "；;。":
            out.append("".join(buf))
            buf = []
        elif depth == 0 and ch in "，," and POLICY_NOTE_PAT.search(s[i + 1:i + 10]):
            out.append("".join(buf))
            buf = []
    if buf:
        out.append("".join(buf))
    return out


def _key_first(s):
    """把「本级无原文 / 申报口径以本级为准」的说明簇提到字段最前。

    客户可见窗口有限（B 端 SOURCE_DOC_MAX 字、C 端另裁 44 字），口径句若排在末尾
    会被截断吞掉，客户就会把省级原文误认成本市政策 —— 这是实质口径误导，不是排版问题。
    前置 = 只调顺序、零信息损失；文号/标题段留在原位，不被带前。

    三处细节（实测踩出来的）：
      1) 口径说明常与文号同句，用 `；` 分隔 → 先分句，命中的那句若以「因…」开头，
         从因果连词处再切一刀，只把说明部分提前，文号留在后面；
      2) 说明常跨两句（「因X市…暂无原文页…；政策内容一致，申报口径以X市…为准」）
         → 命中的段若与后继段同属说明簇，整簇一起提前，避免切在半句上；
      3) 前置段末尾统一收成 `；`，避免出现 `。；` 连标点。
    """
    segs = _split_sents(s)
    hit = next((i for i, g in enumerate(segs) if POLICY_NOTE_PAT.search(g)), -1)
    if hit < 0:
        return s
    m = _CAUSAL_LEAD.search(segs[hit])
    if m and m.start() > 0:                       # 段内文号在前、说明在后 → 再切一刀
        segs[hit:hit + 1] = [segs[hit][:m.start()], segs[hit][m.start():]]
        hit += 1
    if hit == 0:
        return s                                  # 已在最前，无需搬
    keyed, j = [segs[hit]], hit + 1
    while j < len(segs) and POLICY_NOTE_PAT.search(segs[j]):
        keyed.append(segs[j])                     # 同簇说明段一并提前
        j += 1
    lead = "".join(keyed).strip().rstrip("；;。") + "；"
    rest = "".join(segs[:hit] + segs[j:]).strip()
    return (lead + rest).rstrip("；;") if rest else lead.rstrip("；")


def source_doc(rec):
    """政策依据：抽出「文号 + 标题」，去掉长链接尾巴；只有链接时回退抓文号。

    输出即客户可见文本，两端共用（B 端「政策依据」列 / C 端卡片溯源行），
    保证「三端同源」。口径句一律前置，避免被截断窗口吞掉。
    """
    s = _s(rec.get("source_doc"))
    s = re.sub(r"https?://\S+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ，,；;。、")
    if not s:
        # 早期条目 source_doc 只写了链接：从 deadline 等字段里回捞文号
        blob = " ".join(_s(rec.get(k)) for k in ("deadline", "notes", "std_name"))
        m = DOC_NO.search(blob)
        s = (m.group(0).strip() + "（原文见办理入口）") if m else "官方来源见办理入口"
    s = _key_first(s)
    return s[:SOURCE_DOC_MAX] + ("…" if len(s) > SOURCE_DOC_MAX else "")


def clip_note_visible(s, n):
    """裁到 n 字，但**保证口径句落在窗口内**（否则窗口平移到该句起点）。

    用于客户可见窗口极短处（C 端卡片 44 字）。`_key_first` 已把绝大多数口径句搬到最前，
    但口径句嵌在括号内时搬不动（实测踩到），此时宁可窗口只显示「无本级原文」
    的说明句、也不让客户把省级原文档成本级政策 —— 窗口平移不删内容，零信息损失。
    """
    s = re.sub(r"\s+", " ", _s(s)).strip()
    if len(s) <= n:
        return s
    if POLICY_NOTE_PAT.search(s[:n]):
        return s[:n].rstrip("，,；;、 ") + "…"
    m = POLICY_NOTE_PAT.search(s)
    if not m:
        return s[:n].rstrip("，,；;、 ") + "…"
    j = max(s.rfind(c, 0, m.start()) for c in "；;。，,") + 1
    seg = s[j:j + n].strip(" ，,；;、")
    return ("…" + seg) if seg else (s[:n] + "…")


def report_unmapped():
    if not UNMAPPED:
        return "映射完整：无未识别枚举值。"
    lines = ["⚠️ 发现未映射的枚举值（已在成品中原样保留，请补充 enum_map.json）："]
    for f, vs in UNMAPPED.items():
        for v, n in sorted(vs.items(), key=lambda x: -x[1]):
            lines.append(f"  - {f} = {v!r}  × {n}")
    return "\n".join(lines)
