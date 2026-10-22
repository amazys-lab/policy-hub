# -*- coding: utf-8 -*-
"""成品矩阵 · 唯一真值源（2026-10-12 新增）

**为什么要有这个文件**（元规则三问之③「判据成文了吗」）：

`output/` 下的成品（B 端 3 份 Excel + C 端 2 份 Excel + C 端单城 Excel）此前**只存在于
出成品时的那几条命令行里** —— 谁出过、用什么配方出的、应该有多少条，代码里没有任何声明。
后果（本批实测）：
  · `tests/test_output_gate.py` 的 OUTPUTS 停在 **v20261007**，而当前成品是 v20261012
    → 断言守着的是一份两版前的旧文件，**当前成品零覆盖**（还没红，因为它对缺文件 skip）。
  · `pipeline/verify_output.py` 的默认路径停在 **v20261006**。
  · 「改了数据/判据但没重出成品」**零断言可拦** —— 这正是本项目最重要的一条教训
    （改数据不重出成品 → `str(None) == "None"` 印进客户可见单元格）。

★ **C 端 PDF 线已于 2026-10-20 退役**（商业方向收敛，不再做资料售卖；见 `JOBS` 处注记）。
  `export_pdf.py` 模块**保留**：它仍是 `DOMAIN_ORDER` / `PRODUCTS` / `is_person` 的
  真值源（`export_excel` / `audience` / 本文件的城市清单都从它取）。

所以这里把**配方**与**验收口径**声明一处：
  · `pipeline/export_excel.py` / `export_pdf.py` 出成品 → 读这里的 JOB（人工执行时对齐）；
  · `tests/test_output_sync.py` 验收成品 → **读同一份 JOB 重算条数**，不另写判据。

★ 刻意**不在这里硬编码任何条数**（如「545」）：条数由 `recalc_rows(job)` 从源库现算。
  硬编码的数字会在下一次数据改动时变成"假绿"—— 断言应该比数据活得久。
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT_DIR = os.path.join(ROOT, "output")
C_OUT_DIR = os.path.join(OUT_DIR, "C端")

# ── 配方声明 ────────────────────────────────────────────────────────────────
# kind   = "excel" | "pdf"
# preset = loader.PRESETS 的键（excel）／export_pdf.PRODUCTS 的键（pdf）
# scope  = "region"（原文照出）| "province"（跨城归并 + 覆盖率标注）
# title  = 仅供 excel 定位文件名（与 export_excel.derive_title 的结果一致）
EXCEL_JOBS = [
    dict(key="excel:gd_region", kind="excel", preset="gd", scope="region",
         title="广东（珠三角）",
         note="B 端对外主推款：珠三角 9 市，原文照出（不归并，靠「城市」列区分）"),
    dict(key="excel:all", kind="excel", preset="all", scope="region",
         title="已收录城市",
         note="B 端对外全量款：全库（城市数从数据现算，不写死）。"
              "★ 2026-10-13 改名：「全国」→「已收录城市」—— 库里只有 4 省 15 城，"
              "自称「全国」是**无据的地理主张**（判据 = `export_excel.check_title_scope`；"
              "与标题同源的 `PRESET_TITLES['all']` 必须一起改，否则 path_of 找不到文件）。"),
    dict(key="excel:gd_province", kind="excel", preset="gd", scope="province",
         title="广东省",
         note="B 端省总表：跨城归并（省级→「广东全省」、国家级→「全国」）"),
    # ── C 端（个人读者）：多城改出 Excel（2026-10-12）───────────────────────
    # 用户实测：单城 63 条用 PDF 刚好；珠三角 255 / 全国 385 条时 PDF 得线性翻完，
    # 「先记政策名、再找城市」两维人工扫 → 改 Excel 用城市列筛选定位。
    # 收录口径 = `audience.is_person`（与 C 端 PDF 同一份判据）。
    dict(key="excel:c_prd", kind="excel", audience="c", preset="prd", scope="region",
         title="珠三角9市个人补贴清单",
         note="C 端多城包：区域打包，只收个人/创业者/海外人才可申报"),
    dict(key="excel:c_all", kind="excel", audience="c", preset="all", scope="region",
         title="已收录城市个人补贴清单",
         note="C 端全库包：全库，只收个人/创业者/海外人才可申报。"
              "★ 2026-10-13 改名：「全国14城个人补贴清单」→「全国个人补贴清单」→ 本名。"
              "第一次去掉了**会随采集增长的城市数**（新增城市后实际 15 城 → 字面失真）；"
              "第二次去掉了**无据的地理主张**（库里只有 4 省 15 城）。"
              "名字与 export_pdf.PRODUCTS 的 fname 必须一致（否则 path_of 找不到文件，S3 会红）。"),
]

# ── C 端单城 PDF（2026-10-14 改造）──────────────────────────────────────────
# 「一城一 PDF」= C 端的单城交付单元：读者关心的是「我这座城市能领什么」，
# 不是区域打包清单 —— 单城册子的标题**天然就是搜索词**。
#
# ★ 城市清单**从数据现算**，不硬编码（§5x：凡会随采集增长的一律不写死）。
#   上一版把某城写成 `pdf:sz` 一条固定 job —— 新增城市后不会自动多出册子。
# ★ `pdf:sz` 这个 key 现在由 `city_pdf_jobs()` 产出，且**文件名不变**
#   （`resolve_preset("city_sz")["fname"] == PRODUCTS["sz"]["fname"]`），
#   既有成品路径不受影响。
# ★ `export_pdf.PRODUCTS` 里的 prd / all / gd_prov 代码路径**保留**（多城城市优先编排
#   + 书签），仍被 tests/test_pdf_layout.py 以 `build_html()` 现造样本验证；
#   只是当前**无产品出** —— 不要因为"没人用"就删掉那条已验证的渲染路径。
#
# 阈值：单城不足 CITY_PDF_MIN_ROWS 条**不单独成册**（某城 8 条 ⇒ 留在区域合集里）。
# **这是产品判断不是技术限制** —— 8 条的册子会显得"内容太少"。取 15 是因为
# 常见最小单城（20 条）与单域城（8 条）之间有明显断层，中间值最稳。
CITY_PDF_MIN_ROWS = 15


def codes_over_threshold(cnt, threshold):
    """判据内核（**纯函数**，可注入合成数据单测）：给定 `城市 → 条数` 计数，返回达标城市码（升序）。

    ★ 为什么单独抽出来（2026-10-17，`84-` §4）：
      `city_pdf_jobs()` 刻意不接收参数（「传参就等于允许调用方写死清单」），
      于是「阈值是否真的生效」无法用合成数据验证 —— 自检只能拿**真实数据**佐证，
      而真实数据是会变的：存量 16 城**全部** ≥ 阈值时，`len(full) > base` 恒假，
      断言随采集进度随机变红（技能 §5z-10：**锚点禁锚「当前数据状态」**）。
      内核纯函数化后，`test_P5` 用合成计数做**真双向**自检，与数据解耦。
    ★ 边界：**等于阈值算达标**（`>=`），这是产品口径，防"差一"回归。
    """
    return [c for c in sorted(cnt) if cnt[c] >= threshold]


def city_pdf_jobs():
    """现算「可单独成册」的城市 → PDF job 列表（按城市码排序，顺序稳定可复现）。

    ★ 刻意**不接收参数**：城市清单只能来自源库，传参就等于允许调用方写死清单。
    """
    from collections import Counter

    import audience
    import export_pdf as EP
    import loader

    rows = [r for r in loader.filter_active(loader.load_all(ROOT)) if audience.is_person(r)]
    cnt = Counter(r.get("city") for r in rows)
    out = []
    for code in codes_over_threshold(cnt, CITY_PDF_MIN_ROWS):
        preset = EP.CITY_PREFIX + str(code).lower()
        prod = EP.resolve_preset(preset)      # 顺带校验城市码已在 mappers 注册（未注册会抛）
        # `title` 与产品定义同源 —— 让 test_product_naming 的 N2/N4 能直接覆盖单城 PDF
        # （此前 C_JOBS 只含 C 端 Excel，单城的命名与范围主张零覆盖）。
        out.append(dict(key="pdf:%s" % preset, kind="pdf", preset=preset,
                        title=prod["fname"],
                        note="C 端上架单元：%s 单城 %d 条" % (prod["scope"], cnt[code])))
    return out


PDF_JOBS = city_pdf_jobs()
# ★ 2026-10-20：C 端 PDF 线退役（不再做资料售卖）。`PDF_JOBS` **保留但不再进 JOBS**：
#   它现算的「可单城成册城市清单」仍是单城 Excel 的城市真值源（test_city_excel /
#   test_product_naming 从这里取），函数名不改 —— 改名=两处引用同步，零收益。
#   重出 PDF 的能力（export_pdf.main）随之冻结，不删除 —— 真值源模块不能动。


# ── C 端单城 Excel（与单城 PDF **一一对应**，2026-10-14）──────────────────────
# 起因：使用者反馈「PDF 里的链接点不动，只能复制链接去浏览器看」。
#   根因是 PDF 的**点击依赖读者阅读器**（微信内置阅读器 / 部分手机 App 不吃
#   link annotation），属交付形态的**固有风险**，不是数据问题。
#   Excel 三条都稳：① 超链接在 Excel / WPS 里必定可点；② 单元格值本身就是 URL（可复制）；
#   ③ 支持按「城市 / 政策类别 / 数据深度」筛选。
# ⇒ 每座城市同时给「PDF 阅读版 + Excel 可查版」：同名同源，按习惯选。
#
# ★ 城市清单**只从 `city_pdf_jobs()` 取** —— 单一真值源。另写一份城市筛选必然分叉
#   （本项目已因"两套判据分叉"踩过 4 次）。阈值也自然共用（某城 8 条同样不出）。
def city_excel_jobs():
    return [dict(key="excel:%s" % j["preset"], kind="excel", audience="c",
                 preset=j["preset"], title=j["title"],
                 note="C 端单城**筛选用表**（与 `%s` 同名同源）" % j["key"])
            for j in PDF_JOBS]


# ★ 显式追加而非改写上方静态表：静态 5 条（B 端 3 + C 端多城 2）保持可读，
#   单城由现算产出（城市增长时自动跟着变，不物化 —— §5x）。
EXCEL_JOBS = EXCEL_JOBS + city_excel_jobs()

# 2026-10-20：JOBS 只含 Excel。原 `JOBS = EXCEL_JOBS + PDF_JOBS` 中 PDF 部分退役 ——
# C 端单城 Excel（city_excel_jobs，由 PDF_JOBS 的城市清单派生）全部保留。
JOBS = EXCEL_JOBS


# ── 版本 ────────────────────────────────────────────────────────────────────
def _const_from_source(path, name):
    """AST 读模块级字符串常量（**不 import** —— 导出器顶层有 I/O 副作用，见技能 §5i）。"""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    v = node.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        return v.value
    return None


def exporter_version(kind):
    """kind ∈ {"excel","pdf"} → 该导出器的 VERSION 字面量（读不到返回 None）。"""
    return _const_from_source(os.path.join(HERE, "export_%s.py" % kind), "VERSION")


def versions():
    return {"excel": exporter_version("excel"), "pdf": exporter_version("pdf")}


def current_version():
    """当前版本号。两端不一致时抛错 —— 那本身就是要拦的事故。

    **真事故原型**：B 端与 C 端分成两次发布，若只改了一端的 VERSION，
    客户拿到「Excel v20261012 + PDF v20261011」两个时点的同一份政策 —— 售后无解。
    """
    v = versions()
    if not v["excel"] or not v["pdf"]:
        raise RuntimeError("读不到导出器 VERSION：%r" % v)
    if v["excel"] != v["pdf"]:
        raise RuntimeError("B 端 / C 端版本不一致：excel=%s pdf=%s" % (v["excel"], v["pdf"]))
    return v["excel"]


# ── 路径 ────────────────────────────────────────────────────────────────────
def pdf_meta(preset):
    """C 端配方真值源 = `export_pdf.resolve_preset`（不在这里另抄一份 fname / cities）。

    ★ 2026-10-14：由 `PRODUCTS[preset]` 改为 `resolve_preset(preset)` ——
      后者同时支持静态产品与**现算的单城产品**（`city_<码>`）。单城产品刻意不物化
      进 `PRODUCTS`（城市数会增长，物化就是写死），直接用 `PRODUCTS[preset]` 会 KeyError。
      静态 preset 上两者返回**同一对象**，`test_output_sync` 的 identity 断言仍成立。
    """
    import export_pdf as EP
    return EP.resolve_preset(preset)


def path_of(job, version=None):
    v = version or current_version()
    if job["kind"] == "excel":
        if job.get("audience") == "c":
            # C 端 Excel 与 C 端 PDF 同目录、同命名习惯（`{产品名}_{版本}.xlsx`），
            # 一份是筛选用表、一份是阅读用册，拿到的是一套。
            return os.path.join(C_OUT_DIR, "%s_%s.xlsx" % (job["title"], v))
        return os.path.join(OUT_DIR, "%s政策补贴总表_%s.xlsx" % (job["title"], v))
    return os.path.join(C_OUT_DIR, "%s_%s.pdf" % (pdf_meta(job["preset"])["fname"], v))


def html_of(job, version=None):
    """C 端 PDF 的同源 HTML（导出器与 PDF 一同写出，是 PDF 的直接输入）。"""
    v = version or current_version()
    return os.path.join(C_OUT_DIR, "%s_%s.html" % (pdf_meta(job["preset"])["fname"], v))


# ── 重算（验收口径）────────────────────────────────────────────────────────
def recalc_rows(job):
    """按成品同款判据从源库重算记录。

    **必须复用导出器自己的模块**（loader / cross_city / export_pdf.PRODUCTS / audience.is_person），
    不在这里另写一份过滤逻辑 —— 本项目因"两套判据分叉"踩过 4 次。
    C 端 Excel（`audience="c"`）与 C 端 PDF 走**同一份**产品定义与收录判据，
    所以两者条数必然一致（`test_output_sync.py` 的 S3 同时校验两侧）。
    """
    import loader
    all_rows = loader.load_all(ROOT)

    if job["kind"] == "excel":
        if job.get("audience") == "c":
            # C 端口径：产品定义与收录判据都取自 C 端 PDF 导出器（不另写一份）
            import export_pdf as EP
            # ★ 2026-10-14：走 `resolve_preset` 而非直接下标 —— 单城产品（`city_<码>`）
            #   是现算的、不在静态 `PRODUCTS` 里，直接下标会 KeyError。
            prod = EP.resolve_preset(job["preset"])
            rows = loader.filter_active(loader.filter_cities(all_rows, prod["cities"]))
            return [r for r in rows if EP.is_person(r)]
        cities = loader.PRESETS.get(job["preset"])
        rows = loader.filter_active(loader.filter_cities(all_rows, cities))
        if job.get("scope") == "province":
            import cross_city
            import mappers as M
            prov = sorted({M.province(c) for c in (cities or [])} - {""})[0]
            rows, _ = cross_city.merge(rows, province=prov,
                                       all_rows=loader.filter_active(all_rows))
        return rows

    import export_pdf as EP
    prod = pdf_meta(job["preset"])
    rows = loader.filter_active(loader.filter_cities(all_rows, prod["cities"]))
    rows = [r for r in rows if EP.is_person(r)]
    if prod.get("province"):
        import cross_city
        rows, _ = cross_city.merge(rows, province=prod["province"],
                                   all_rows=loader.filter_active(all_rows))
    return rows


# ── 源库判据（"改了就必须重出成品"的输入集）────────────────────────────────
# 刻意**只收会改变客户可见内容**的输入：
#   · domains/**/*.json         记录本体
#   · collector/link_audit.json 选链 / 降级判据（决定成品里渲染哪个链接）
#   · common/enum_map.json      城市 / 省份 / 类别等**中文名映射**（成品里每个中文字都来自它）
#   · common/geo.json           省内地级市全名单（决定省表「已收录 N/M」的 M）
# **不收** pipeline/*.py —— 否则改任意一行代码都要重出 6 份成品，断言会被人删掉。
# （代码改动的影响面由 `recalc_rows` 的条数对账来兜。）
#
# ★ 2026-10-12 增补后两者：本轮修城市码时发现 —— `enum_map.city` 少一个键，
#   成品「城市」列就会印出英文码（**客户可见**），但旧输入集对它视而不见（"改了不必重出"）。
def source_inputs():
    out = []
    for root, _dirs, files in os.walk(os.path.join(ROOT, "policy_hub", "domains")):
        out += [os.path.join(root, f) for f in files if f.endswith(".json")]
    for extra in (os.path.join(ROOT, "policy_hub", "collector", "link_audit.json"),
                  os.path.join(HERE, "enum_map.json"),
                  os.path.join(ROOT, "policy_hub", "common", "geo.json")):
        if os.path.exists(extra):
            out.append(extra)
    return out


def latest_source_mtime():
    """返回 (最新 mtime, 计入文件数)。输入集为空时返回 (None, 0)。"""
    fs = source_inputs()
    if not fs:
        return None, 0
    return max(os.path.getmtime(p) for p in fs), len(fs)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("版本：", versions())
    print("源库最新 mtime：", latest_source_mtime())
    print()
    for j in JOBS:
        p = path_of(j)
        n = len(recalc_rows(j))
        exists = os.path.exists(p)
        print("%-22s 期望 %4d 条  %s  %s"
              % (j["key"], n, "✅存在" if exists else "❌缺失", os.path.relpath(p, ROOT)))
