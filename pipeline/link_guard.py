# -*- coding: utf-8 -*-
"""L5 · 出成品前链接降级（2026-10-09 新增，26- 方案 L5）

目的 —— 给商业兜底：**即使外部网站明天改版，客户拿到的成品里也只会看到文号，
不会点到坏链/错链。**

判据来源（单一真值源）：源库 `policy_hub/collector/link_audit.json`
—— 由 `link_verify.py` 对全库 URL 做页面归类（2026-10-09 起含「非原文文种页」判据）。
导出器**不另造词典**（本项目已因"两套判据分叉"踩过 3 次，见技能 §四第 23 项）。

降级规则（保守原则：缺证据不动手）
  · 任一角色（guide_url / apply_url）：
        404/死链 · 不可达 · 已失效 · 登录墙            → 降级
  · guide_url 专属（文种错 = 客户可见的标签/内容不符，见技能 §6.18-4）：
        非原文文种页 · 政策解读页 · 新闻/动态页 · 栏目/聚合页 → 降级
  · **不降级**：未归类、SPA 应用页、办事入口页、办事指南页、政策清单页、PDF附件原文
        （"不知道"≠"坏"）

选链判据（2026-10-10 三端口径统一）：
  `guide_slot_ok()` —— 「政策原文」槽位**只收原文类文种**（原文页/政策清单页/PDF附件原文/未归类）。
  与「降级」是两道不同的闸：降级管"要不要把它藏起来"，选链管"该不该把它放到这个槽位"。
  三道闸 = should_degrade（坏链/明文文种错）+ 形态黑名单（R2，URL 就是办事/申报入口）
          + 文种白名单（含 R3：未归类 + .pdf → 抓不到正文，不可当原文）。
  HTML 原文优先于 PDF 附件（R1，见 `mappers.original_doc_url`）。

用法（导出器里接一行）：
    import link_guard as LG
    AUDIT = LG.load_audit()
    g, a, notes = LG.degrade(rec, AUDIT)      # 拿到可直接渲染的安全链接
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))

try:
    from loader import DEFAULT_SRC
except Exception:                                    # 独立运行时兜底（仓内相对，不硬编码盘符）
    DEFAULT_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUDIT_PATH = os.path.join(DEFAULT_SRC, "policy_hub", "collector", "link_audit.json")

# ── 官方域名判据（2026-10-10 收口，真值源 = L2 的 CITY_DOMAINS）─────────────────
# 背景（见工作区 45- 报告 §3）：官方域名判据此前在 4 处各写一份，其中 3 处判错 ——
#   `verify_output.py` 用裸子串 `"gov.cn" in url`，`export_pdf.py` 用 `endswith("gov.cn")`，
#   `link_verify.py` 硬编码 `endswith("gx12333")`（缺 .net 后缀，从未生效）。
#   实测后果：真官方域名 `www.gx12333.net`（政策原文指定的线上申领链接）被全线误报，
#   而 `gov.cn.evil.com` / `fakegov.cn` 这类伪装域名反被裸子串放行（假阳性 + 假阴性同时存在）。
# 现收口为**一套判据**：`.gov.cn` 精确后缀 ∪ CITY_DOMAINS 并集中非 .gov.cn 的官方域名。
#
# 真值源读取方式：**按路径 AST 解析** `post_collect_check.py` 的 `CITY_DOMAINS` 字面量，
#   而不是 `import` 该模块 —— 它顶层有 `sys.stdout=io.TextIOWrapper(...)`，import 会替换
#   sys.stdout 并吞掉调用方尚未 flush 的输出（已实测）。
# 与 `policy_hub/collector/link_verify.is_official_host()` 是同源孪生实现，
#   两侧行为由 `tests/test_official_domain.py` 的对撞断言锁死。
GOV_SUFFIX = ".gov.cn"
_CITY_DOMAINS_SRC = os.path.join(DEFAULT_SRC, "policy_hub", "collector", "post_collect_check.py")


def _load_official_extra():
    """从 L2 真值源 CITY_DOMAINS 派生「非 .gov.cn 的官方域名」集合（如 gx12333.net）。

    读不到就返回空集（此时只认 .gov.cn）—— 宁严勿松，且由测试断言真值源可读。
    """
    try:
        import ast
        with open(_CITY_DOMAINS_SRC, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except Exception:
        return frozenset()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "CITY_DOMAINS" for t in node.targets):
            continue
        try:
            cd = ast.literal_eval(node.value)
        except Exception:
            return frozenset()
        out = set()
        for ds in cd.values():
            for d in ds:
                d = str(d).strip().lstrip(".").lower()
                if d and d != "gov.cn" and not d.endswith(GOV_SUFFIX):
                    out.add(d)
        return frozenset(out)
    return frozenset()


OFFICIAL_EXTRA = _load_official_extra()


def is_official_host(host_or_url):
    """host（或整条 URL）是否为库认可的官方域名。**出成品层的唯一判据入口**。"""
    h = (host_or_url or "").strip().lower()
    if "//" in h:
        h = h.split("//", 1)[1]
    h = h.split("/")[0].split("?")[0].split("#")[0].split(":")[0].strip(".")
    if not h:
        return False
    if h == "gov.cn" or h.endswith(GOV_SUFFIX):
        return True
    return any(h == s or h.endswith("." + s) for s in OFFICIAL_EXTRA)


# 任一角色降级（确定点不开 / 不该点）
DEAD_ANY = {"404/死链", "不可达", "已失效", "登录墙"}

# ★ 2026-10-14：**`apply_url` 不因「登录墙」降级**（原 DEAD_ANY 对两个角色一视同仁 → 改判据）。
#   理由：「线上申报系统打开即要账号」是**业务属性**，不是链接缺陷（技能 §5z-5）。
#     · 挂出来 → 客户看到「去哪儿办」，进去自己注册；
#     · 降级成空白 → 客户**什么也看不到**，且成品文案「入口暂不可用，请咨询当地主管部门」
#       对「只是要登录」的官方申报系统是**误导**。
#   实测影响面极小：全库被归类「登录墙」的 URL 仅 2 个，其中仅 1 个作 `apply_url`
#   （某市涉企服务平台登录页，官方申报指南原文点名）。
#   其余三类对两个角色都成立（原文页/入口页死了都是一样的死），故仍降。
DEAD_APPLY = {"404/死链", "不可达", "已失效"}

# 仅 guide_url 降级（文种错 = 客户可见的标签/内容不符），分两档：
#   默认档：**明文**文种错（标题写着问答/指引/汇总/新闻），客户一看就知道挂错了 → 降
#   严格档（--link-strict）：再加上 栏目/聚合页、政策解读页、新闻/动态页
#     这几类多为**存量数据问题**（记录本就没有合格原文页，靠 sources 兜底凑数）。
#     隐藏它们会让数据问题"看不见"，不利治理 —— 故默认只列台账、不动成品：
#     `link_guard.py --audit-report` 输出完整 179 条清单，作为数据治理输入。
WRONG_KIND_GUIDE_DEFAULT = {"非原文文种页"}
WRONG_KIND_GUIDE_STRICT = {"非原文文种页", "政策解读页", "新闻/动态页", "栏目/聚合页"}

ROLE_LABEL = {"guide_url": "政策原文链接", "apply_url": "办理入口"}

# ---------------- 「政策原文」槽位可接受的文种（2026-10-10 三端口径统一） ----------------
# 背景：`mappers.original_doc_url()` 原来按「路径像不像政策原文」挑链，会挑到
#       办事指南页 / 公示页 / 新闻页，甚至 404 —— 客户在成品里点「政策原文」被喂错。
# 判据（技能 §5h 文种铁律）：**「政策原文：查看原文」这个标签挂什么，就只能收什么文种**。
#   收：原文页 / 政策清单页（清单本身即政策依据）/ PDF附件原文；
#       未归类 = 缺证据不动手（与下方「不降级」原则一致）→ 放行，否则三端又分叉。
#   不收：办事指南页 / 办事入口页 / 栏目聚合页 / 政策解读页 / 非原文文种页 /
#         新闻动态页 / SPA 应用页 / 404死链 / 不可达 / 已失效 / 登录墙。
GUIDE_OK_KINDS = {"原文页", "政策清单页", "PDF附件原文", "未归类",
                  # ★ 2026-10-18（`96-`）新增：分类器把「200 但静默抓取拿不到正文」的页面
                  #   从「未归类」里单列出来（`link_verify.CLS_EMPTY`）。
                  #   **为什么仍然收**：准入面本来就没变 —— 这些 URL 此前全部算「未归类」，
                  #   而「未归类」就在白名单里。收紧成"一律降级"会**静默丢掉**客户浏览器
                  #   明明能打开的官方政策详情页（实测某条：某市企业综合服务平台
                  #   `/qykj/publicDetail/1667`，客户能看到全文，静态抓只能拿到 23 字符）。
                  #   「我们抓不到」≠「客户看不到」—— 不能拿爬虫的能力当交付标准。
                  #   **变的是可见性与举证责任**：新类名让这 113 个页面从「未归类」里浮出来，
                  #   且每个「正文空壳当原文」的链接必须在 `known_issues["guide_url_shell"]`
                  #   登记理由，否则闸门第 27 项直接红（见 `gate_validate.check_shell_guide`）。
                  "正文空壳(无法静态核验)",
                  # ★ 2026-10-18（`97-`）新增：Word/Excel/WPS 附件（`link_verify.CLS_OFFICE`）。
                  #   公文最常见的载体之一；此前没有说话的位置 —— `.doc` 被当 HTML 解码，
                  #   上万字符二进制乱码冒充「正文」，页面滑到「未归类」。与 PDF 同属原文类。
                  "Office附件原文"}
EMPTY_KIND = "正文空壳(无法静态核验)"
OFFICE_KIND = "Office附件原文"

# 「原文类」内部再分层（2026-10-10 R1）：HTML 原文优先于 PDF 附件。
#   实测动机：同一记录里既有 HTML 原文页又有 PDF 附件时，附件常常**不是原文**：
#     · 某扩岗补助条目 → PDF 实为**符合发放条件名单公示**（公示名单）
#     · 某科技企业条目 → 4 页**无文本层扫描件**（无法核验）
#   附件里的文种（名单/表格/扫描件）无法靠路径判断，故让 HTML 原文页先选，PDF 只作兜底。
HTML_GUIDE_KINDS = {"原文页", "政策清单页"}
PDF_GUIDE_KIND = "PDF附件原文"
# ★ 2026-10-18（`97-`）：附件层 = PDF + Office。两者都是「附件」，文种无法靠路径判断，
#   同属 `mappers.original_doc_url()` 的第二层（HTML 原文优先）。
ATTACH_GUIDE_KINDS = {"PDF附件原文", "Office附件原文"}

# ── V6「政策原文链接」空值上限（★ 唯一真值源，2026-10-12）─────────────────────
# B 端 `verify_output.py` 与 C 端 `export_pdf.py` **两处**都要判这一条。
# 分叉史：此前一处写模块常量 `NO_ORIG_MAX_RATE`、一处写死字面量 `0.05`，
#   仅靠注释互相提醒 → 改一处漏一处没人发现（本项目已因"两套判据分叉"踩过 5 次）。
# 现收口到此处；`tests/test_v6_dual_impl.py` 以 AST 断言两处都必须引用本函数，
#   且两份源码里不得再出现裸 `0.05`。
# 口径：确无公开原文页是**合法状态**（§5h），故设下限 5 条容错；
#   但为空比例过高 = 选链判据被改坏 / 基线丢失 → 必须红（防"静默全空"）。
NO_ORIG_MAX_RATE = 0.05
NO_ORIG_MIN = 5


def no_orig_limit(total):
    """「政策原文链接」引用空值的允许上限 = max(5 条, 5%)。"""
    return max(NO_ORIG_MIN, int(NO_ORIG_MAX_RATE * int(total or 0)))


def no_orig_overflow(n_no_orig, total):
    """V6 空值是否超限。返回 `(超限?, 上限)` —— B/C 两处共用，结论必然一致。"""
    limit = no_orig_limit(total)
    return int(n_no_orig or 0) > limit, limit


# ── V6「办理入口」空值判据（★ 2026-10-17 由「上限阈值」改为「对账」）──────────
# 改造原因（事故原型，见 `86-` 报告 §2）：
#   原判据 `no_entry_overflow(空条数, 总条数)` 用 `max(5, 5%)` 上限。
#   但该阈值是**在「渲染层兜底已生效」的世界里校准的** ——
#   `mappers.entry_url()` 会把 `apply_url` 为空、`guide_url` 合格的记录**无条件**回退成
#   原文页 ⇒ 成品「办理入口」空值几乎恒为 0~1 条 ⇒ 上限判据**从未真正生效过**。
#   2026-10-17 取消该回退后（成品如实留空），按源库口径实测：
#   已收录 **118 条空 vs 上限 46** ⇒ 20/20 份成品全红。
#   **看起来像数据崩了，实际是阈值基准错** —— 兜底把空值消灭了，阈值按「几乎无空值」定的。
#
# ⇒ 正解不是调阈值（那是「放宽判据」，铁律不许），而是**换测量方式：对账**。
#   成品「办理入口」空条数 **必须 ==** 源库 `apply_url` 为空的条数。
#   与 V9「申报条件对账」同构 —— 本项目已证明「对账比非空率硬」：
#     · 成品空得更多 ⇒ 渲染层把该填的填丢了（回退链被关 / 漏读）
#     · 成品空得更少 ⇒ 渲染层**凭空造了入口**（旧兜底干的正是这件事）
#   两种都必须红。
#
# ★ 沿革（不要退回阈值）：`OS-HP-201` 事故时 V6 对空值**一律判红** ⇒ 逼运营每格硬塞链接
#   ⇒ 改「上限判据」（2026-10-13）⇒ 但上限又被兜底架空（本注释）⇒ 改对账（2026-10-17）。
#   教训：**判据的测量面必须与它要防的缺陷同层**（数据层缺陷要在数据层测）。
def entry_reconcile(n_out, n_src):
    """「办理入口」空值对账。返回 `(平?, 差)`；差 = 成品空 − 源库空。"""
    out, src = int(n_out or 0), int(n_src or 0)
    return out == src, out - src

# 形态黑名单（R2）：URL **形态本身**就是「办事 / 申报 / 查询入口」→ 不论基线怎么归类都不可入槽。
# 每一条都来自**实测打开看内容**（技能 §6.18-4：能打开 ≠ 是原文），不是猜的：
NON_GUIDE_URL_PAT = re.compile(
    r"/portal/guide-combo/"            # 某省政务服务网「一件事」事项页，
                                       #   正文 = 办事指南/在线办理/申请材料（基线判「未归类」被放行）
    r"|/portal/guide/"                 # 同上：政务服务网事项指南页
    # ★★ 2026-10-18（`97-`）**移除** `/qykj/projectDetail/`（某市企业空间项目页）。
    #   移除理由不是"它变好了"，而是**当初的加入理由被证伪**：注释原文是
    #   「SPA 空壳（抓回正文仅 10 字节）」—— 这是拿**我们抓不抓得到**当否决依据。
    #   `96-` §77.2 已实测推翻这一依据：同一站点的 `/qykj/publicDetail/1667` 静态只有
    #   23 字符，但**浏览器渲染后是政策全文**（`NB-HS-001` 因此必须保留）。
    #   同一 SPA 的两个兄弟路径不能一个按形态封杀、一个靠台账放行 —— 那是**判据自相矛盾**。
    #   现在二者统一：归类「正文空壳」⇒ 可进原文槽，但**必须逐条进 `known_issues.guide_url_shell`
    #   写明理由**（闸门第 28 项），未登记直接红。**红比静默降级好**：降级会把客户能打开的
    #   官方政策详情页悄悄换成「原链暂不可用」。
    #   保留 `hrs.nbrc.com.cn/download/`：它的理由是**文种**（PDF 正文体例 = 办事指南），
    #   与抓取能力无关 —— ★ 形态黑名单只许收「文种」理由。
    r"|hrs\.nbrc\.com\.cn/download/"   # NB-EMP-019：人才服务网下载区 PDF，正文为
                                       #   「政策内容/适用对象/申请流程/申报材料」= 办事指南体例，非原文
)


def guide_slot_ok(url, audit, strict=False):
    """该 URL 能否作为「政策原文」渲染给客户。

    三道闸：① 先过 should_degrade（确定点不开 / 明文文种错）；
            ② 过形态黑名单（URL 形态 = 办事/申报/查询入口）；
            ③ 过文种白名单（只有「原文类」能进这个槽位）。
    """
    if not url or not str(url).startswith("http"):
        return False
    if should_degrade(url, "guide_url", audit, strict):
        return False
    if NON_GUIDE_URL_PAT.search(str(url)):
        return False
    kind = cls_of(url, audit) or "未归类"
    # R3：「未归类」= 基线没抓到内容。若它还是个 .pdf，说明抓不到正文（可能是扫描件，
    #     也可能是链接已跳走）→ 不能凭"猜"把它当原文（实测：生效页已跳回门户首页）。
    if kind == "未归类" and str(url).lower().split("?")[0].endswith(".pdf"):
        return False
    return kind in GUIDE_OK_KINDS

# 成品里给客户看的文案：**中性、不含内部术语**
# （客户不应看到"非原文文种页""栏目/聚合页"这类内部判据词；原因只进台账）
CLIENT_TEXT = {
    "guide_url": "（原链暂不可用，请按文号检索原文）",
    "apply_url": "（入口暂不可用，请咨询当地主管部门）",
    "both": "（链接暂不可用，请按文号检索原文）",
}


def load_audit(path=None):
    """读页面归类 {url: {class, status, host}}；文件缺失返回 {}（此时不降级）。"""
    p = path or AUDIT_PATH
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("urls") or {}


def cls_of(url, audit):
    return str((audit.get(url) or {}).get("class") or "")


def should_degrade(url, role, audit, strict=False):
    """返回降级原因字符串；不需要降级返回 None。

    strict=False（默认）＝ 只降「确定点不开」+「明文文种错」；
    strict=True  ＝ 连 栏目/聚合页、解读页、新闻页一并降（成品更干净，但会掩盖存量数据问题）。
    """
    if not url or not str(url).startswith("http"):
        return None
    cls = cls_of(url, audit)
    dead = DEAD_APPLY if role == "apply_url" else DEAD_ANY
    if cls in dead:
        return "%s不可用（%s）" % (ROLE_LABEL.get(role, role), cls)
    if role == "guide_url":
        kinds = WRONG_KIND_GUIDE_STRICT if strict else WRONG_KIND_GUIDE_DEFAULT
        if cls in kinds:
            return "政策原文链接指向「%s」，非原文页" % cls
    return None


def degrade(rec, audit, strict=False):
    """返回 (guide_url, apply_url, notes)。notes = [(role, reason), ...]。"""
    out = {}
    notes = []
    for role in ("guide_url", "apply_url"):
        u = rec.get(role) or ""
        if not isinstance(u, str):
            u = ""
        reason = should_degrade(u, role, audit, strict)
        if reason:
            notes.append((role, reason))
            u = ""
        out[role] = u
    return out["guide_url"], out["apply_url"], notes


def note_text(notes):
    """给内部台账用的可读降级说明（含判据词，**不要**直接给客户看）。"""
    return "；".join(r for _, r in notes)


def client_text(notes):
    """给成品用的中性文案（客户可见，不得含内部术语）。"""
    roles = {r for r, _ in notes}
    if not roles:
        return ""
    if roles >= {"guide_url", "apply_url"}:
        return CLIENT_TEXT["both"]
    return CLIENT_TEXT["guide_url" if "guide_url" in roles else "apply_url"]


# ---------------- 自检（元规则三问②：工具可信吗 → 加自检样本） ----------------

def selftest(verbose=True):
    audit = {
        "https://a.gov.cn/dead.html": {"class": "404/死链"},
        "https://b.gov.cn/qa.html": {"class": "非原文文种页"},
        "https://c.gov.cn/ok.html": {"class": "原文页"},
        "https://d.gov.cn/entry": {"class": "办事入口页"},
        "https://e.gov.cn/unknown": {"class": "未归类"},
        "https://f.gov.cn/column": {"class": "栏目/聚合页"},
        "https://g.gov.cn/guide": {"class": "办事指南页"},
        "https://h.gov.cn/list": {"class": "政策清单页"},
        "https://i.gov.cn/att.pdf": {"class": "PDF附件原文"},
        "https://j.gov.cn/expired": {"class": "已失效"},
    }
    cases = [
        # (说明, rec, 期望 guide 降级, 期望 apply 降级, strict)
        ("死链·任一角色都降级",
         {"guide_url": "https://a.gov.cn/dead.html", "apply_url": "https://a.gov.cn/dead.html"}, True, True, False),
        ("明文文种错（问答页）·默认即降，apply_url 保留",
         {"guide_url": "https://b.gov.cn/qa.html", "apply_url": "https://d.gov.cn/entry"}, True, False, False),
        ("栏目/聚合页·默认**不降**（存量问题只记台账）",
         {"guide_url": "https://f.gov.cn/column", "apply_url": ""}, False, False, False),
        ("栏目/聚合页·strict 档降级",
         {"guide_url": "https://f.gov.cn/column", "apply_url": ""}, True, False, True),
        ("正常原文页 + 办事入口页·都不降级",
         {"guide_url": "https://c.gov.cn/ok.html", "apply_url": "https://d.gov.cn/entry"}, False, False, False),
        ("未归类·不降级（缺证据不动手）",
         {"guide_url": "https://e.gov.cn/unknown", "apply_url": ""}, False, False, False),
        ("空值/非 URL·不降级",
         {"guide_url": "", "apply_url": None}, False, False, False),
    ]
    ok = True
    for desc, rec, eg, ea, st in cases:
        g, a, notes = degrade(rec, audit, strict=st)
        # 断言必须看「是否记录了降级」，不能看「结果是否为空」——
        # 输入本来就是空值的用例会让后者假失败（本自检第一版的实际 bug）。
        roles = {r for r, _ in notes}
        good = (("guide_url" in roles) == eg) and (("apply_url" in roles) == ea)
        ok = ok and good
        if verbose:
            print("  [%s] %s%s" % ("OK " if good else "FAIL", desc,
                                   ("  → " + note_text(notes)) if notes else ""))
    if verbose:
        print("L5 链接降级自检：%s" % ("✅ 通过" if ok else "❌ 失败"))

    # ---- 「政策原文」槽位文种白名单自检（2026-10-10，双向断言）----
    slot_cases = [
        ("原文页 → 可入槽", "https://c.gov.cn/ok.html", True),
        ("PDF附件原文 → 可入槽", "https://i.gov.cn/att.pdf", True),
        ("政策清单页 → 可入槽", "https://h.gov.cn/list", True),
        ("未归类 → 可入槽（缺证据不动手）", "https://e.gov.cn/unknown", True),
        ("不在基线 → 可入槽（缺证据不动手）", "https://zz.gov.cn/never-seen", True),
        # R2 形态黑名单（3 条均来自实测）
        ("政务服务事项页（形态黑名单）→ 不可入槽",
         "https://www.gdzwfw.gov.cn/portal/guide-combo/11440300052799993U444TC110FT000", False),
        ("企业空间项目页（形态黑名单）→ 不可入槽",
         "https://qf.ningbo.gov.cn/qykj/projectDetail/51623", False),
        ("人才网下载区 PDF（形态黑名单）→ 不可入槽",
         "https://hrs.nbrc.com.cn/download/sshbsshbzzcsm.pdf", False),
        # R3：未归类 + .pdf
        ("未归类 + .pdf（抓不到正文）→ 不可入槽",
         "https://www.suzhou.gov.cn/x/files/abc.pdf", False),
        ("基线已确认 PDF附件原文 → 仍可入槽（R3 不误伤）", "https://i.gov.cn/att.pdf", True),
        ("办事指南页 → 不可入槽", "https://g.gov.cn/guide", False),
        ("办事入口页 → 不可入槽", "https://d.gov.cn/entry", False),
        ("栏目/聚合页 → 不可入槽", "https://f.gov.cn/column", False),
        ("非原文文种页 → 不可入槽", "https://b.gov.cn/qa.html", False),
        ("404/死链 → 不可入槽", "https://a.gov.cn/dead.html", False),
        ("已失效 → 不可入槽", "https://j.gov.cn/expired", False),
        ("空串 → 不可入槽", "", False),
        ("非 URL → 不可入槽", "见附件", False),
    ]
    ok2 = True
    for desc, u, want in slot_cases:
        got = guide_slot_ok(u, audit)
        good = got == want
        ok2 = ok2 and good
        if verbose:
            print("  [%s] %s（期望 %s）" % ("OK " if good else "FAIL", desc, want))
    if verbose:
        print("政策原文槽位文种白名单自检：%s" % ("✅ 通过" if ok2 else "❌ 失败"))
    return 0 if (ok and ok2) else 1


def audit_report(out_md=None):
    """扫全库（成品口径：走 mappers 的 original_doc_url / entry_url），
    输出两档降级清单 —— 这是「数据治理」的直接输入。"""
    import collections
    import datetime
    import mappers as M
    import loader as L

    audit = load_audit()
    allr = L.load_all()
    c = collections.Counter()
    rows = []
    for r in allr:
        gu, au = M.original_doc_url(r, audit), M.entry_url(r)
        for strict in (False, True):
            _, _, notes = degrade({"guide_url": gu, "apply_url": au}, audit, strict)
            if notes:
                for role, reason in notes:
                    c[(strict, reason.split("（")[-1].rstrip("）").split("，")[0])] += 1
                if not strict:
                    rows.append((r.get("id"), r.get("city"), M.entry_url(r), gu, note_text(notes)))
    p = out_md or os.path.join(_HERE, "_link_degrade_report.md")
    L2 = ["# 成品链接降级清单（L5 · 数据治理输入）", "",
          "> 生成：%s｜扫描：%d 条记录（成品口径，走 mappers 的 original_doc_url/entry_url）"
          % (datetime.datetime.now().isoformat(timespec="seconds"), len(allr)), ""]
    L2.append("## 一、默认档会被降级的记录（%d 条）" % len(rows))
    L2.append("")
    L2.append("判据：确定点不开（404/死链·不可达·已失效·登录墙）+ 明文文种错（非原文文种页）")
    L2.append("")
    L2.append("| 记录 | 城市 | 会降级的链接 | 原因 |")
    L2.append("|---|---|---|---|")
    for rid, city, u, gu, why in rows:
        L2.append("| `%s` | %s | %s | %s |" % (rid, city, (gu or u)[:70], why))
    L2.append("")
    L2.append("## 二、两档口径统计")
    L2.append("")
    L2.append("| 档 | 类别 | 条数 |")
    L2.append("|---|---|---|")
    for (strict, cls), n in sorted(c.items(), key=lambda x: (x[0][0], -x[1])):
        L2.append("| %s | %s | %d |" % ("strict" if strict else "默认", cls, n))
    open(p, "w", encoding="utf-8").write("\n".join(L2))
    print("默认档降级 %d 条 → %s" % (len(rows), p))
    for (strict, cls), n in sorted(c.items(), key=lambda x: (x[0][0], -x[1])):
        print("  %-6s %-16s %d" % ("strict" if strict else "默认", cls, n))
    return 0


if __name__ == "__main__":
    import argparse
    import sys

    ap = argparse.ArgumentParser(description="L5 链接降级判据（自检 / 清单）")
    ap.add_argument("--audit-report", action="store_true",
                    help="扫全库输出两档降级清单（数据治理输入）")
    a = ap.parse_args()
    if selftest() != 0:
        sys.exit(1)
    if a.audit_report:
        sys.exit(audit_report())
    sys.exit(0)
