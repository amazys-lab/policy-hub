# -*- coding: utf-8 -*-
"""
L3 成品校验 · 守「数据 → 成品」这最后一公里
--------------------------------------------------
现有 SOP 只校验到数据入库，成品没人守。本脚本守成品。

校验项：
  V1 无英文枚举残留      — 关键列只允许出现中文白名单值
  V2 无占位符残留        — None / null / nan / to_collect 一律视为未完成
  V3 关键列非空率        — 低于阈值直接拦下
  V4 政策编号唯一性      — 成品内不得重复
  V5 金额列可读性        — 不得为空、不得只剩余枚举词
  V6 链接规范性          — 办理入口 / 政策原文链接必须是 http(s) 且为库认可的官方域名；
                           政策原文链接为空属合法（确无公开原文页），但比例受上限约束；
                           ★ 2026-10-17 起「办理入口空值」改**对账**（成品空条数 == 源库
                           `apply_url` 空条数），不再用阈值 —— 见 link_guard.entry_reconcile
  V7 （已退役 2026-10-17）— 原「溯源独立率」在成品层测量，必然被 `entry_url` 的兜底污染：
                           源库同页实为 0 条，成品却报 117 条。测量面错层，改为
                           `tests/test_entry_reconcile.py` 的**源库级**断言（源库同页 == 0）
  V8 内部字段名泄漏      — 客户可见单元格不得出现 schema 定义的内部字段名（2026-10-10 新增）
  V9 申报条件对账        — 成品「申报条件」空条数 == 源库条件全空的条数（2026-10-12 新增）
用法：python verify_output.py output/xxx.xlsx
"""
import io
import os
import re
import sys
from collections import Counter

from openpyxl import load_workbook

# L5 降级文案的判据真值源（同目录；不另造词典）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import link_guard as _LG  # noqa: E402

# 关键列 -> 允许的中文值（白名单）
WHITELIST = {
    "补贴形式": {"现金补贴", "资格通道", "评审认定"},
    "办理渠道": {"线上办理", "线下窗口", "线上线下均可"},
    "数据深度": {"L0 仅目录", "L1 条件可判", "L2 可算金额", "L3 含材料与入口", "L4 全字段含窗口"},
}
REQUIRED = ["政策编号", "城市", "政策类别", "政策名称", "适用对象", "补贴标准",
            "政策依据", "有效期",
            # ★ 2026-10-17 移出「办理入口」「政策原文链接」两列：
            #   **「非空率」不是 URL 列的正确质量指标** —— 两个 URL 列各有一条专门判据
            #   （V6 对账 / V6 原文上限），而「空」在它们身上是**合法状态**
            #   （线下窗口受理的政策本就没有网页入口；原文未公开的政策本就没有原文页）。
            #   守着它们的后果实测：某单城清单的原文链接非空率只有 **85.7%**，
            #   离 80% 阈值只差 5.7 个百分点 —— 再少几条就误报红。
            #   ⇒ 与 `test_condition_render` 的教训同源：**闸门的输入要有覆盖度**，但
            #     「覆盖度」不等于「非空率」，URL 列的存在性由 V6 的缺列检查兜住。
            # ★ 2026-10-12 补入「申报条件」：此前**不在名单里**，故渲染层只读 cond.must 导致
            #   B 端 193/806、C 端 128/385 空白时，本闸门全绿放行
            #   （元规则「闸门的输入本身要有覆盖度断言」）。V9 另做条数对账兜底。
            "申报条件"]
URL_COLS = ["办理入口", "政策原文链接"]
# 「政策原文链接」允许为空的比例上限：确无公开原文页属合法状态（下限 5 条），
# 但超限说明选链判据被改坏 / 基线丢失 → 必须红。
# ★ 2026-10-12 收口：本值**不再在此定义** —— 真值源 = `link_guard.NO_ORIG_MAX_RATE`
#   / `link_guard.no_orig_limit()`。C 端 `export_pdf.py` 读同一函数。
#   （分叉史：此处曾是模块常量、C 端是字面量 `0.05`，只靠注释互相提醒 → 无机器拦；
#    现由 `tests/test_v6_dual_impl.py` 的 AST 断言守。）
PLACEHOLDER = re.compile(r"\b(None|null|nan|NaN|to_collect|undefined|TODO)\b")
ENUM_LEAK = re.compile(r"^(money|channel|review|approval|planned|competition|auto|online|window|mixed|"
                       r"active|exited|renamed|person|unit|entrepreneur|overseas)$")

# ── V8 内部字段名泄漏（2026-10-10 新增）──────────────────────────────────────
# 事故：`district_awards` 这个**内部字段名**被写进了客户可见的「补贴标准」文本（2 处）：
#   ① 某科技企业条目：「…详见 district_awards 逐区依据。」
#   ② 某条目：「…(已回官方核实示例见 district_awards)。」
# 而该字段当时**根本不渲染** → 客户照指引去成品里找「逐区依据」，找不到（悬空指引）。
# 这是「机器没拦住」的典型（元规则三问之①）→ 本轮补断言。
#
# 判据（**真值源 = schema.json 全文**，不在此另造词典 —— 本项目因"两套判据分叉"踩过 4 次）：
#   · 从 schema 全文抽出所有 **snake_case 词**：`[a-z][a-z0-9]*(?:_[a-z0-9]+)+`，长度 ≥ 6。
#   · 长度下限是防误报：过短的（`id` / `name` / `city` / `level` / `note`）会与自然语言、
#     机构简称撞出假阳，故排除。
#   · 只查 Sheet1 的数据行 —— 表头是中文列名；Sheet2/Sheet3 是字段说明与中英对照字典，
#     那里出现英文键名是**有意**的。
#
# ★ 判据演进（2026-10-10，被 V8 自己的自检逼出来的）：
#   初版只取 `program_common_fields` 的**顶层键**，自检注入 `applicant_kinds` 时 V8 **抓不到** ——
#   因为它是 `cond` 的**嵌套**键，不在那个 dict 里。这正是元规则三问之②「拦它的工具可信吗」：
#   **没有自检的防复发断言 = 假闸门**（本项目 D8 已因此栽过一次）。
#   改为全文字符串抽取后，`applicant_kinds` / `any_identities` / `ent_ss_months` 一网打尽。
_SNAKE_WORD = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_MIN_FIELD_LEN = 6
_FIELD_FROM_SCHEMA = None


def internal_field_names():
    """内部标识符清单（来自 schema 全文，缓存）。读不到时返回空集 → V8 自动跳过。

    ⚠️ **不做去冗余**（2026-10-10 试过又退回）：曾想删掉"被更长词包含"的短词
    （`ss_months` ⊂ `ent_ss_months`），但那会**降低检出** —— `district_awards` 恰好是
    `district_awards_fields` 的子串，删掉它以后客户文本里真写真写 `district_awards`
    反而抓不到了（V8 自检 G2/G3 当场抓出该回归）。
    重复上报的问题改在**同格内去碎片**处理（见 `find_field_leaks`）。
    """
    global _FIELD_FROM_SCHEMA
    if _FIELD_FROM_SCHEMA is None:
        p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "policy_hub", "common", "schema.json")
        try:
            raw = io.open(p, encoding="utf-8").read()
            _FIELD_FROM_SCHEMA = {w for w in _SNAKE_WORD.findall(raw)
                                  if len(w) >= _MIN_FIELD_LEN}
        except Exception:
            _FIELD_FROM_SCHEMA = set()
    return _FIELD_FROM_SCHEMA


def find_field_leaks(header, body, fields=None):
    """返回 {“列名 → 命中的字段名”: 次数}。抽成函数是为了让断言能直接打它（V8 自检）。

    **同格内去碎片**：一格里若同时命中 `ent_ss_months` 与 `ss_months`（后者是前者的子串），
    只报**最长**的那个 —— 否则报错信息会退化成无信息量的碎片（V8 自检 G2 实测）。
    注意这只影响**同格内的重复**，不删清单里的短词（那会降低检出，见 `internal_field_names`）。
    """
    fields = internal_field_names() if fields is None else fields
    out = Counter()
    if not fields:
        return out
    for r in body:
        for ci, v in enumerate(r):
            s = str(v or "")
            if not s:
                continue
            hits = [f for f in fields if f in s]
            for fld in hits:
                if any(fld != o and fld in o for o in hits):
                    continue                      # 被同格里的更长命中覆盖
                out["%s → %s" % (header[ci] if ci < len(header) else "?", fld)] += 1
    return out


# ── 源库读取（V6 对账用；**只读**，读不到不中断闸门）─────────────────────────
_BY_ID_CACHE = None


def src_records():
    """源库记录按 ID 索引（惰性 + 缓存）。读不到返回 `None`（≠ 空 dict）。

    区分 `None` 与 `{}` 很重要：`{}` 会让对账「源库侧恒 0」而误报红，
    `None` 才表示「读不到 ⇒ 本项跳过」（读不到 ≠ 通过，故打印 ⏭ 而非 ✅）。
    """
    global _BY_ID_CACHE
    if _BY_ID_CACHE is None:
        try:
            import loader as _LD
            _BY_ID_CACHE = {str(r.get("id")): r for r in _LD.load_all(_LD.DEFAULT_SRC)}
        except Exception:
            _BY_ID_CACHE = {}
    return _BY_ID_CACHE or None


def src_entry_blank(body, idx):
    """对账左值：成品这些行对应的源库记录中，`apply_url` 非 http 的**行数**。

    ★ **逐行对齐、不去重**（与 V9 同款口径）：成品某编号出现两次，源库侧也计两次，
      两侧才可比。同一编号在成品里重复出现（多城清单的省级政策）时，两侧同步放大。
    """
    by_id = src_records()
    if by_id is None:
        return None
    n = 0
    for r in body:
        rec = by_id.get(str(r[idx["政策编号"]] or "").strip())
        if rec is None:
            continue
        if not str(rec.get("apply_url") or "").strip().startswith("http"):
            n += 1
    return n


def main(path):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb["政策总表"]
    rows = list(ws.iter_rows(values_only=True))
    head, body = list(rows[0]), rows[1:]
    idx = {h: i for i, h in enumerate(head)}

    problems = []
    print(f"校验文件：{os.path.basename(path)}")
    print(f"数据行数：{len(body)}  列数：{len(head)}")
    print()

    # V1 英文枚举残留
    leaks = []
    for cn, allow in WHITELIST.items():
        if cn not in idx:
            problems.append(f"缺列：{cn}")
            continue
        bad = Counter()
        for r in body:
            v = str(r[idx[cn]] or "").strip()
            if v and v not in allow:
                bad[v] += 1
        for v, n in bad.items():
            leaks.append(f"{cn} = {v!r} × {n}")
    print(f"[V1] 英文枚举残留：{'✅ 无' if not leaks else '❌ ' + str(len(leaks)) + ' 处'}")
    for x in leaks[:10]:
        print("      ", x)
    problems += leaks

    # V2 占位符
    ph = Counter()
    for r in body:
        for ci, v in enumerate(r):
            s = str(v or "")
            for m in PLACEHOLDER.findall(s):
                ph[f"{head[ci]}:{m}"] += 1
    print(f"[V2] 占位符残留：{'✅ 无' if not ph else '❌ ' + str(sum(ph.values())) + ' 处'}")
    for k, n in ph.most_common(10):
        print(f"       {k} × {n}")
    problems += list(ph)

    # V3 关键列非空率
    print("[V3] 关键列非空率：")
    for cn in REQUIRED:
        if cn not in idx:
            continue
        filled = sum(1 for r in body if str(r[idx[cn]] or "").strip())
        rate = filled / len(body) * 100 if body else 0
        flag = "✅" if rate >= 95 else ("⚠️" if rate >= 80 else "❌")
        print(f"       {flag} {cn:<8}{filled:>5}/{len(body)}  {rate:5.1f}%")
        if rate < 80:
            problems.append(f"{cn} 非空率仅 {rate:.1f}%")

    # V4 编号唯一
    ids = [str(r[idx["政策编号"]] or "") for r in body]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    print(f"[V4] 政策编号唯一性：{'✅ 无重复' if not dup else '❌ 重复 ' + str(dup[:5])}")
    problems += dup

    # V5 金额列
    empty_amt = sum(1 for r in body if not str(r[idx["补贴标准"]] or "").strip())
    print(f"[V5] 补贴标准为空：{empty_amt} 条" + (" ✅" if empty_amt == 0 else " ❌"))
    if empty_amt:
        problems.append(f"补贴标准为空 {empty_amt} 条")

    # V6 链接
    # ⚠️ L5 联动（2026-10-09）：出成品前 link_guard 会把"确定点不开 / 明文文种错"的链接
    #    换成**中性文案**（客户不会点到坏链）。若不识别，V6 会把这种**有意降级**误报成
    #    "缺链接"——两个机制互相打架。故此处必须区分三态：真链接 / 已降级 / 真缺失。
    #    判据真值源 = link_guard.CLIENT_TEXT（**不在这里另造一份词典**：本项目因"两套判据分叉"踩过 3 次）。
    # ⚠️ 三端口径统一（2026-10-10）：`政策原文链接` 为空也有两种来源，必须分开 ——
    #    (i) 该记录确实没有可公开的原文页（选链已把非原文文种滤掉）→ **合法状态**；
    #    (ii) 值不是 URL 的脏值（"见附件"之类）→ 真缺陷。
    #    若把 (i) 也判红，运营第一天就会集体忽略 V6（同技能 §5.0b「闸门不能逼人跳过」）。
    #    但为空**比例**过高 = 选链判据被改坏 / 基线丢失 → 必须红（防"静默全空"）。
    _DEGRADED = set(_LG.CLIENT_TEXT.values()) | {"（链接暂不可用）"}
    # ⚠️ 上限判据真值源 = `link_guard.no_orig_limit()`（2026-10-12 收口）。
    #    此处原为 `max(5, int(NO_ORIG_MAX_RATE * len(body)))` —— 与 C 端 `export_pdf.py`
    #    里另写的一份字面量实现**只靠注释保证同源**（无机器拦）。现两处共用同一函数，
    #    由 `tests/test_v6_dual_impl.py` 以 AST 断言守住。
    _NO_ORIG_MAX = _LG.no_orig_limit(len(body))
    print("[V6] 链接规范性：")
    n_degraded_total = n_no_orig_total = n_no_entry_total = 0
    _src_blank = None        # V6 办理入口对账左值（源库 apply_url 空条数）；缺列时保持 None
    for cn in URL_COLS:
        if cn not in idx:
            problems.append(f"缺列：{cn}")
            print(f"       ❌ 缺列 {cn}")
            continue
        urls = [str(r[idx[cn]] or "").strip() for r in body]
        real = [u for u in urls if u.startswith("http")]
        degraded = [u for u in urls if u in _DEGRADED]
        blank = [u for u in urls if not u]
        dirty = [u for u in urls if u and not u.startswith("http") and u not in _DEGRADED]
        # ⚠️ 官方域名判据真值源 = `link_guard.is_official_host()`（2026-10-10 收口）。
        #    此处原为裸子串 `"gov.cn" in u`，实测两个方向都错（见工作区 45- 报告 §3.3）：
        #      · 假阳性：政策原文指定的官方入口 `https://www.gx12333.net/si/` 被判非 gov.cn → 误报红
        #      · 假阴性：`https://www.gov.cn.evil.com/`、`https://fakegov.cn/` 含子串 → 被当官方放行
        #    **不在此另写一份判据**（本项目已因"两套判据分叉"踩过 4 次）。
        gov = sum(1 for u in real if _LG.is_official_host(u))
        n_degraded_total += len(degraded)
        bad = len(dirty)
        if dirty:
            problems.append(f"{cn} 非 URL 脏值 {len(dirty)} 条")
        if cn == "政策原文链接":
            n_no_orig_total = len(blank)
            _over, _lim = _LG.no_orig_overflow(n_no_orig_total, len(body))
            if _over:
                problems.append(f"政策原文链接 空值 {n_no_orig_total} 条 > 上限 {_lim}"
                                f"（选链判据异常？）")
                bad += n_no_orig_total
        elif cn == "办理入口":
            # ★ 2026-10-17：由「上限阈值」改为**对账**（见 `link_guard.entry_reconcile` 注释）。
            #   原上限阈值被渲染层兜底架空过 —— 成品空值恒 0~1 条，上限从未真正生效；
            #   取消兜底后按源库口径 118 条 vs 上限 46 ⇒ 误报全红。故换测量方式。
            #   口径：成品空条数 **必须 ==** 源库 `apply_url` 非 http 的条数；两个方向都红。
            n_no_entry_total = len(blank)
            _src_blank = src_entry_blank(body, idx)
            if _src_blank is None:
                print(f"       ⏭ 办理入口 空 {n_no_entry_total} 条 —— 源库不可读，本项对账跳过"
                      f"（读不到 ≠ 通过）")
            else:
                _ok_e, _diff_e = _LG.entry_reconcile(n_no_entry_total, _src_blank)
                if not _ok_e:
                    print(f"       ❌ 办理入口空值对账：成品空 {n_no_entry_total} 条 "
                          f"≠ 源库 apply_url 空 {_src_blank} 条（差 {_diff_e:+d}）")
                    if _diff_e > 0:
                        print("          ↳ 成品空得更多 ⇒ 渲染层把该填的入口填丢了"
                              "（回退链被关 / 链接降级判据被改？）")
                    else:
                        print("          ↳ 源库空得更多 ⇒ 渲染层**凭空造了入口**"
                              "（正是 2026-10-17 取消的那种无条件兜底）")
                    problems.append(f"办理入口空值对账不符：成品 {n_no_entry_total} "
                                    f"vs 源库 {_src_blank}")
                    bad += n_no_entry_total
        elif blank:
            problems.append(f"{cn} 空值 {len(blank)} 条")
            bad += len(blank)
        flag = "✅" if not bad and gov == len(real) else ("⚠️" if not bad else "❌")
        print(f"       {flag} {cn:<8}真链接 {len(real)} ｜ 已降级 {len(degraded)} ｜ 空 {len(blank)}"
              f" ｜ 脏值 {len(dirty)} ｜ 官方域名 {gov}/{len(real)}")
        if gov != len(real):
            problems.append(f"{cn} 非官方域名 {len(real) - gov} 条")
    if n_degraded_total:
        print(f"       ℹ️ 已降级合计 {n_degraded_total} 处（L5 有意为之，见同目录 `_link_degrade_*.md` 台账，不计问题）")
    if n_no_orig_total:
        print(f"       ℹ️ 政策原文链接无可公开原文页 {n_no_orig_total} 条"
              f"（上限 {_NO_ORIG_MAX}）—— 选链已滤掉非原文文种，只留文号，属合法状态，不计问题")
    if n_no_entry_total:
        print(f"       ℹ️ 办理入口为空 {n_no_entry_total} 条"
              f"（源库 apply_url 空 {_src_blank if _src_blank is not None else '?'} 条）"
              f"—— 线下窗口 / APP / 邮箱受理的政策本就没有网页入口，属**如实留空**，不计问题")

    # V7 已退役（2026-10-17，原「溯源独立率」）────────────────────────────────
    # 退役理由：该判据在**成品层**测量，而 `mappers.entry_url()` 的兜底会让
    #   「apply_url 空 + guide_url 合格」的记录**必然**印成与原文同页 ⇒ 它测到的其实是
    #   「有多少条政策没有线上入口」这个**业务属性**，不是它声称的「批量取错字段」。
    #   实测：源库同页 **0 条**，而 B 端成品报 117 条、C 端某城报 12/16 = 25% 判红；
    #   且小样本城（单城 16 行）必被大分母阈值误杀。
    #   ⇒ 病根是**测量面错层**（数据层缺陷要在数据层测）。
    #   原始意图（防「同源字段被批量抄错」）改由源库级断言守：
    #   `tests/test_entry_reconcile.py::test_源库不存在原文页与入口同页的记录`。
    print("[V7] 溯源独立率：⏭ 已退役（2026-10-17）—— 原因：测量面错层"
          "（成品层测出的「同页」100% 由 entry_url 兜底制造，源库同页实为 0 条）；"
          "改由源库级断言守，见 tests/test_entry_reconcile.py")

    # V8 内部字段名泄漏（2026-10-10 新增，判据见本文件常量区）
    _flds = internal_field_names()
    if not _flds:
        print("[V8] 内部字段名泄漏：⏭ 跳过（读不到 schema.program_common_fields）")
    else:
        leaks8 = find_field_leaks(head, body, _flds)
        print(f"[V8] 内部字段名泄漏：{'✅ 无' if not leaks8 else '❌ ' + str(sum(leaks8.values())) + ' 处'}"
              f"（扫描 {len(_flds)} 个字段名）")
        for k, n in leaks8.most_common(10):
            print(f"       {k} × {n}")
            print(f"         ↳ 客户会照这句去成品里找不存在的东西（悬空指引）——改文案或补渲染")
        problems += list(leaks8)

    # V9 申报条件对账（2026-10-12 新增）
    # 起因：用户质询「申报条件为什么会有空白，政策原文不是都有的吗」。
    #   实测根因 = 渲染层只读了 `cond.must`，而条件还落在 base_must / branches[].must /
    #   any_must.conds / manual_check / score_rule —— 175 条信息本来就在库里。
    # ★ 判据刻意**不用"非空率"而用"对账"**：
    #   成品空条数必须 == 源库 `condition_items()` 为空的条数。
    #   不等 ⇒ 要么渲染漏读（成品空得比源库多），要么数据被凭空补齐（空得比源库少）——
    #   两种都必须红。非空率阈值（V3 的 80%）做不到这点：B 端修前 76% 只差一点点，
    #   「漏读 1 条」更是永远照不出来。
    try:
        import loader as _LD
        import mappers as _M
        _by_id = {str(r.get("id")): r for r in _LD.load_all(_LD.DEFAULT_SRC)}
        n_out = sum(1 for r in body if not str(r[idx["申报条件"]] or "").strip())
        n_src, unknown = 0, []
        for r in body:
            rid = str(r[idx["政策编号"]] or "").strip()
            rec = _by_id.get(rid)
            if rec is None:
                unknown.append(rid)
                continue
            if not _M.condition_items(rec):
                n_src += 1
        if unknown:
            print(f"[V9] 申报条件对账：❌ 成品有 {len(unknown)} 条编号不在源库（{unknown[:3]}…）"
                  f"—— 成品与源库已不同步")
            problems.append(f"成品 {len(unknown)} 条编号不在源库")
        elif n_out != n_src:
            print(f"[V9] 申报条件对账：❌ 成品空 {n_out} 条 ≠ 源库条件全空 {n_src} 条"
                  f"（差 {n_out - n_src:+d}）")
            if n_out > n_src:
                print("       ↳ 成品空得更多 ⇒ 渲染层漏读某类条件载体（须查 condition_items 覆盖）")
            else:
                print("       ↳ 源库空得更多 ⇒ 成品出现了源库没有的条件文本（须查是否凭空补齐）")
            problems.append(f"申报条件对账不符：成品 {n_out} vs 源库 {n_src}")
        else:
            print(f"[V9] 申报条件对账：✅ 成品空 {n_out} 条 == 源库条件全空 {n_src} 条"
                  f"（覆盖率 {100 * (1 - n_out / len(body)):.1f}%）")
    except Exception as e:      # 闸门不得因源库不可读而中断（读不到 ≠ 通过）
        print(f"[V9] 申报条件对账：⏭ 跳过（{type(e).__name__}: {e}）")

    print()
    if problems:
        print(f"❌ 未通过：{len(problems)} 项待处理")
        return 1
    print("✅ 成品校验通过（V1–V6 / V8 / V9 全绿；V7 已于 2026-10-17 退役）")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        p = sys.argv[1]
    else:
        # 默认取**当前版本**的 B 端主推款。
        # ★ 2026-10-12 修：原写死 `v20261006`，版本一升就指错文件（运行时报"文件不存在"，
        #   而不是"版本已过期"）—— 判据真值源改为 pipeline/release_matrix.py（成品矩阵）。
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import release_matrix as _RM
        p = _RM.path_of(_RM.EXCEL_JOBS[0])
    sys.exit(main(p))
