# -*- coding: utf-8 -*-
"""跨城归并 · 省总表专用（唯一真值源）

**问题**：省级 / 国家级政策会被**每个市各录一条**。
省总表里同一个国家级税收政策被辖区各市各录一遍 ——
客户打开省表看到 N 条一模一样的「小型微利企业所得税优惠」。
区域包 / 城市分表不暴露此问题，**省表独有**。

**判据（关键：别用 URL）**：
    分组键 = **归一化（政策名称 + 政策依据文号）**，组内城市数 ≥ 2 即跨城组。
    为什么不是 `guide_url`：省政府公报**一个页面可能装着几十个不同政策**，
    按 URL 归并会把它们全合成 1 条 —— 这正是「一链多政策合法」铁律的直接后果。

**适用范围标注（不硬编码任何文号 / 域名）**：
    组内城市**跨省** → 国家级 → 「全国」
    组内城市**同省** → 省级   → 「{省}全省」
    只看组内省份集合，判据可自证、可回归。

**互补效应**（实测副产品，不是本模块的目标但很值）：同一个省政府公报页，
两个市各自只录了其中一部分（交集很小）——
归并后按并集保留，**省表反而比任何单个市都完整**。
"""
import re
from collections import defaultdict

# 归一化：去掉空白与全半角标点，让「（含本数）」与「(含本数)」等写法归到一组
_NORM = re.compile(r"[\s（）()【】\[\]、,，。.；;：:·\-—_/“”\"'']+")


def _norm(s):
    return _NORM.sub("", str(s or ""))


def group_key(rec):
    """归并判据：归一化（名称 + 文号）。名称缺失的记录不参与归并。"""
    return (_norm(rec.get("name")), _norm(rec.get("source_doc")))


def _fullness(rec):
    """字段非空数 —— 用来挑组内信息最全的记录当代表。"""
    n = 0
    for v in rec.values():
        if isinstance(v, str):
            n += 1 if v.strip() else 0
        elif isinstance(v, dict):
            n += 1 if v else 0
        elif isinstance(v, list):
            n += 1 if v else 0
        elif v is not None:
            n += 1
    return n


def scope_of(cities, ref_cities, province=None):
    """层级判定的**唯一实现**（`merge()` 与 `annotate_scope()` 共用，防两份判据分叉）。

    - 组内城市**跨省** → 国家级 → `"全国"`
    - 组内城市**同省** → 省级   → `"{省}全省"`
    - 单城 / 判不出省 → 返回 `""`（调用方自行显示城市本身）

    `ref_cities` = **全库**同组城市（判定必须跳出本表范围，见 `merge()` docstring 反例）。
    """
    import mappers as M
    provs = {M.province(c) for c in (ref_cities or cities)} - {""}
    if len(provs) > 1:
        return "全国"
    if not provs:
        return ""
    p = sorted(provs)[0] if provs else (province or "")
    return f"{p}全省" if p else ""


def annotate_scope(rows, all_rows=None, province=None):
    """给每条记录标注**适用范围**，**不归并、不丢条目**（C 端「标城市」用）。

    与 `merge()` 共用 `group_key()` + `scope_of()`，判据完全同源。
    返回 `{rec_id: scope_city}`，其中 `scope_city` 取值：
      - `"全国"`    → 组内城市跨省（国家级政策）
      - `"{省}全省"` → 组内城市同省且 ≥2 城（省级政策被各市各录一条）
      - `""`        → 单城（调用方显示该城市名，或按产品范围决定不标）

    `all_rows` 必须传**全库**（判「国家级 vs 省级」要跳出本表范围）。
    """
    by_key = defaultdict(list)
    for r in rows:
        by_key[group_key(r)].append(r)

    ref_by_key = defaultdict(list)
    for r in (all_rows if all_rows is not None else rows):
        ref_by_key[group_key(r)].append(r)

    out = {}
    for k, items in by_key.items():
        if not k[0]:                                   # 名称缺失 → 不判
            continue
        cities = {str(r.get("city") or "").upper() for r in items} - {""}
        if len(cities) < 2:                            # 本表内单城 → 不是跨城组
            continue
        ref_cities = {str(x.get("city") or "").upper() for x in ref_by_key.get(k, [])} - {""}
        scope = scope_of(cities, ref_cities, province)
        if scope:
            for r in items:
                out[r.get("id")] = scope
    return out


def scope_labels(rows, all_rows=None, province=None):
    """「适用范围」**客户可见文案**的唯一实现（C 端 PDF / C 端 Excel 共用）。

    返回 `{rec_id: label}`：
      · 组内跨省 → `"全国通用"`
      · 组内同省 → `"{省}全省"`
      · 其余（单城 / 判不出层级）→ `""`，**由调用方决定显示城市名还是不显示**
        （单城产品整本都是同一座城，标了是噪音；多城产品必须标）

    ★ 为什么抽出来（2026-10-12）：C 端多城从 PDF 改出 Excel 后，两种形态都要标适用范围。
      若各写一遍「全国 → 全国通用 / 其余原样 / 空 → 城市名」的映射，
      两端文案就会随改动漂移（本项目已因"两套判据分叉"踩过 4 次）。
    判据内核 = `annotate_scope()`（继续下沉到 `group_key()` + `scope_of()`，单一路径）。
    """
    m = annotate_scope(rows, all_rows, province)
    out = {}
    for r in rows:
        # 省表（已归并）优先用 `merge()` 打好的 `_scope_city`；其余多城产品现场标注
        s = r.get("_scope_city") or m.get(r.get("id")) or ""
        out[r.get("id")] = "全国通用" if s == "全国" else s
    return out


def merge(rows, province=None, all_rows=None):
    """把跨城重复的省级/国家级政策归并为一条并标注适用范围。

    返回 `(new_rows, stat)`：
      - `new_rows` 保持原序，跨城组只留代表记录（附 `_scope_province` / `_scope_city`）；
      - `stat` = {groups, dropped, detail, divergent}，供成品说明与台账用。
    **不修改传入记录**（代表记录是浅拷贝）—— 避免污染 loader 的读取结果。

    `all_rows`（**必须传全库**）：判定「国家级 vs 省级」要**跳出本表范围**看。
    反例（2026-10-10 实测踩到）：只拿广东 9 市出来做省表时，6 个国家级税收政策
    （财政部 / 税务总局文件）在表内城市全属广东 → 被误判「广东全省」。
    正确做法是用全库同组记录的城市集合判：跨省 → 国家级。缺省退化为 `rows`。
    """
    import mappers as M

    by_key = defaultdict(list)
    for i, r in enumerate(rows):
        by_key[group_key(r)].append(i)

    ref_by_key = defaultdict(list)
    for r in (all_rows if all_rows is not None else rows):
        ref_by_key[group_key(r)].append(r)

    replace = {}
    drop = set()
    stat = {"groups": 0, "dropped": 0, "detail": [], "divergent": []}

    for k, idxs in by_key.items():
        if not k[0] or len(idxs) < 2:
            continue
        cities = {str(rows[i].get("city") or "").upper() for i in idxs} - {""}
        if len(cities) < 2:
            continue                                   # 单城 → 不是跨城组

        best = max(idxs, key=lambda i: _fullness(rows[i]))
        # 层级判据用**全库**同组城市，不用本表范围（见 docstring 反例）；
        # 判定内核 = scope_of()，与 annotate_scope() 同源。
        ref_cities = {str(x.get("city") or "").upper() for x in ref_by_key.get(k, [])} - {""}
        scope_city = scope_of(cities, ref_cities, province)
        if not scope_city:                             # 判不出省 → 退回本产品省份口径
            p = province or ""
            scope_city = f"{p}全省" if p else "全国"
        scope_prov = "全国" if scope_city == "全国" else scope_city.replace("全省", "")

        rep = dict(rows[best])
        rep["_scope_province"] = scope_prov
        rep["_scope_city"] = scope_city
        replace[best] = rep
        for i in idxs:
            if i != best:
                drop.add(i)

        stat["groups"] += 1
        stat["dropped"] += len(idxs) - 1
        stat["detail"].append({
            "key": k[0][:40], "scope": scope_city,
            "cities": sorted(cities), "kept": rep.get("id"),
            "n": len(idxs),
        })
        # 组内实质差异检测：不静默 —— 金额表述不一致的组单列出来供人工复核
        amts = {str((rows[i].get("amount") or {}).get("text") or "").strip() for i in idxs
                if isinstance(rows[i].get("amount"), dict)}
        if len({a for a in amts if a}) > 1:
            stat["divergent"].append({
                "key": k[0][:40], "scope": scope_city,
                "n_amount_variants": len({a for a in amts if a}),
            })

    out = [replace.get(i, r) for i, r in enumerate(rows) if i not in drop]
    return out, stat
