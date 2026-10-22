# -*- coding: utf-8 -*-
"""受众口径 · 「谁能申报」的唯一真值源（2026-10-12 新增）

**为什么单独成模块**：

C 端成品（PDF / Excel）的收录口径是「个人 / 创业者 / 海外人才可申报」，B 端是「全量」。
此前 `is_person()` 只存在于 `export_pdf.py` —— C 端多城改出 Excel（`export_excel.py --audience c`）
后，`export_excel.py` 也需要同一判据。若各写一份，就是本项目已踩过 4 次的
「两套判据分叉」：**同一个词在两端含义不同 → 客户看到的两份成品条数对不上**。

所以把判据抽到这里，两端 `import` 同一份：
  · `export_pdf.py`  → `from audience import is_person, kinds_of`（保持 `EP.is_person` 可用）
  · `export_excel.py` → C 端模式同源复用
  · `release_matrix.py` → `recalc_rows()` 用它现算 C 端条数（不另写过滤）

★ **本模块必须零副作用**（技能 §5i：模块顶层禁 I/O）—— 它会被 `release_matrix` /
  `tests/*` 直接 import，顶层任何读文件 / 改 stdout 都会污染 pytest 捕获。
"""
PERSON_KINDS = {"person", "entrepreneur", "overseas", "family"}

# 无 `cond.applicant_kinds` 时的兜底：按政策类别判断这类政策是否面向个人
# 这 6 个域（= `PERSON_FALLBACK_DOMAINS`，2026-10-17 与实现对齐）：
#   就业创业 / 落户 / 技能培训 / 人才引进 / 人才安居 / 大湾区个税。
# 不进兜底的 3 个是「以企业为主」的域：企业用工 / 科技企业 / 普惠税费。
PERSON_FALLBACK_DOMAINS = {
    "employment_startup", "hukou", "vocational_training", "overseas", "housing", "gba_tax",
}


def kinds_of(rec):
    """取一条记录的申报/受益主体集合。

    `cond.applicant_kinds` 优先（申报条件里的细分主体），回退顶层 `applicant_kinds`。
    ★ None 安全（2026-10-09 事故）：null 元素若直接 `str()` 会得到字面量 `"None"`
      混进身份集合 —— 于是"没人能申报"的空值反而匹配上了。
    """
    ks = [x for x in (((rec.get("cond") or {}).get("applicant_kinds")) or []) if x]
    if not ks:
        ks = [x for x in ((rec.get("applicant_kinds") or [])) if x]
    return set(str(x) for x in ks)


def is_person(rec):
    """C 端收录判定：个人 / 创业者 / 海外人才 可申报。"""
    ks = kinds_of(rec)
    if not ks:
        return rec.get("domain") in PERSON_FALLBACK_DOMAINS
    return bool(ks & PERSON_KINDS)
