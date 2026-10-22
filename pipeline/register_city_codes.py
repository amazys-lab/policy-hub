# -*- coding: utf-8 -*-
"""城市码登记（B1）：一次性把新城市码写进 schema.json + enum_map.json + client.html + demo_api.html。

幂等：已存在的城市码自动跳过。字节保真：全部文本手术，换行风格（LF / CRLF）按文件自己走。

覆盖 5 个注册点（缺一个成品就会出错）：
  1) policy_hub/common/schema.json  → city_code（闸门校验合法值）
  2) pipeline/enum_map.json         → city（中文名）/ province（省份）
     ★ 2026-10-12 补：**城市码 → 中文名 / 省份 的唯一真值源**（`M.city()` / `M.province()` /
       `geo.covered_codes()` / `cross_city.scope_of()` 全读它）。原脚本从不写这里，
       导致「schema 在册」被误当「注册完成」——长三角 5 城开工即少报覆盖率、省份列空白。
       受 `tests/test_city_code_consistency.py`（K1–K3）守。
  3) server/static/client.html      → CITY_FIELDS / CITY_NAMES / order ×2
  4) server/static/demo_api.html    → CITY_FIELDS / CITY_NAMES / order ×2

用法：
  python register_city_codes.py            # dry-run，只报告
  python register_city_codes.py --apply    # 写盘

登记完记得重生成字段契约（闸门第 11 项消费它）：
  node <工作区>/pipeline/extract_frontend.js && python <工作区>/pipeline/export_field_contract.py

★ 唯一真值源（2026-10-12 合并）：本脚本原为**两份**（`pipeline/` 与 `policy_hub/collector/`，
  职责相同、各有 141 行差异 → 谁跑了算谁的）。已合并为本文件，collector 版归档于
  `_archive/20261012-city-label-before/dedup/`。`tests/test_city_code_consistency.py::test_k8`
  守「全仓只许一份」。

★★ 2026-10-15 大修：**这份脚本此前是「死」的**。
  它只在「真的有新城要登记」时才暴露问题，而它一直走 `已全部存在，跳过` 的早返回，
  所以四个 latent bug 一直没人发现 —— 直到批 1 开工第一次真登记（29 → 51 码）才连环炸：
    ① `patch_schema` 硬编码 `"\\r\\n  },"` 当块尾锚点，而 schema.json 实为 **LF** ⇒ ValueError；
    ② `_insert_block` 把新条目直接插在 `}` 前 ⇒ 收尾 `}` 被粘到最后一条上（格式脏）；
    ③ `patch_html` 的 CITY_NAMES 锚点写死在 `QZ:"钦州"}` 上 —— 那是「钦州还是队尾」时的快照，
       B1 注册 14 码后队尾已是 `WZ:"温州"}` ⇒ 锚点**永久失配**；
    ④ `assert all(c in chk for c, _, _ in todo)` 按 3 元组解包 4 元组 ⇒ ValueError。
  修法不是「打四个补丁」，而是**把判据内核改成纯函数**（`render_schema` / `render_enum` /
  `render_html` 只吃文本、只吐文本，不碰盘），这样正例与反例能共用同一份实现。
  受 `tests/test_city_onboarding.py`（RC1–RC6）守，其中 RC6 是「锚点不许绑队尾」的**结构性**断言。
"""
import io, json, os, re, sys

# 源库根 = 本文件（pipeline/）的上一级 —— 仓内相对，不再硬编码盘符（T3 · 2026-10-09）
SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(SRC, "policy_hub/common/schema.json")
ENUM = os.path.join(SRC, "pipeline/enum_map.json")
HTMLS = [os.path.join(SRC, "server/static/client.html"),
         os.path.join(SRC, "server/static/demo_api.html")]
# ★ 前端有**第三份副本** `pipeline/_inline.js`（client.html 内联脚本的抽取件，
#   无机器消费方，存在只为守「三处同源」防判据分叉）。
#   ⚠️ 它**不归本脚本管**：它是**抽取件**，追加式打补丁永远追不上（2026-10-15 实测它停在
#      B1 之前：`CITY_NAMES` 共同前缀只有 1326 字符就分叉，`order` 还只有 14 码）。
#      正解 = 由 `node extract_frontend.js` 一并重生成，并由
#      `tests/test_city_onboarding.py::test_rc7` 断言「抽取件 == client.html 的 script 块」，
#      分叉即红 ⇒ 不再可能静默停更。
APPLY = "--apply" in sys.argv

# 队列文档《每日一城_城市队列与日更工作流.md》第四章「城市码登记（避让）」
# (码, schema 全名, 前端简称, 省份)  顺序 = 队列优先级
# ★ 省份列 2026-10-12 补 —— 直辖市（重庆/北京/天津/上海）填自身；省份字符串必须与 geo.json 的
#   provinces 键一致（未登记的省 geo.coverage 返回 total=None，安全跳过，不会算出错数）。
# ★ 前端简称必须与 geo.json 该省名单里的写法**逐字一致** —— geo.coverage 拿它比对，
#   不一致会把已收录城市误报成「缺失」（2026-10-15 扩 geo 全量时特意对齐过）。
#
# ★ 2026-10-15 扩到 **L1 全 36 城**（27 省会 + 5 计划单列市 + 4 直辖市，见 docs/reports/77-）。
#   本批新增 22 码；已登记的不再重复列入（本脚本幂等，列了也只是空转）：
#     · L1 已登记 8：NJ SU HG NB GZ SZ NN CQ QD
#     · L2/L3 已登记 6：WX CH JX NT QU WZ（无锡/常州/嘉兴/南通/泉州/温州）
#   避让台账（★ 全是真实冲突，改码前必读；由队列文档第四章累积而来）：
#     常州   CH  ← CZ 留给河北沧州        ｜ 杭州 HG ← GZ 已属广州、HZ 已属惠州
#     泉州   QU  ← QZ 已属钦州            ｜ 石家庄 SJZ ← SZ 已属深圳
#     兰州   LZH ← LZ 预留给柳州（后备池） ｜ 哈尔滨 HRB ← 铁路/民航惯用码，避开 HEB
#     呼和浩特 HHT ← 不用 HHHT（四字母与全仓 2–3 字母惯例不符）
#     海口   HAK ← 避开 HK（HK 在本仓另有「香港 / 落户域后缀 SZ-HK-*」语义）
#   ⚠️ 后续 L2/L3 加码前**必须先跑全局唯一校验**：DL/YC/GY/LS/LZH/HHT 等已被本批占用，
#      大理、宜春/宜昌、广元、丽水、柳州 等后续城市需另择。冲突时本脚本立即中止，勿手工绕过。
NEW = [
    # —— 批 1 · 省会 10 城（docs/reports/77- §8；★ 本批采集范围＝最小集 2 域）——
    ("CD", "成都市", "成都", "四川"),
    ("WH", "武汉市", "武汉", "湖北"),
    ("CS", "长沙市", "长沙", "湖南"),
    ("ZZ", "郑州市", "郑州", "河南"),
    ("JN", "济南市", "济南", "山东"),
    ("HF", "合肥市", "合肥", "安徽"),
    ("FZ", "福州市", "福州", "福建"),
    ("XA", "西安市", "西安", "陕西"),
    ("SY", "沈阳市", "沈阳", "辽宁"),
    ("KM", "昆明市", "昆明", "云南"),
    # —— 批 2 · L1 其余（凑满 36 城）；直辖市码在此登记 ≠ 采集优先级已定，顺序待拍板 ——
    ("SJZ", "石家庄市", "石家庄", "河北"),
    ("TY", "太原市", "太原", "山西"),
    ("HHT", "呼和浩特市", "呼和浩特", "内蒙古"),
    ("CC", "长春市", "长春", "吉林"),
    ("HRB", "哈尔滨市", "哈尔滨", "黑龙江"),
    ("NC", "南昌市", "南昌", "江西"),
    ("HAK", "海口市", "海口", "海南"),
    ("GY", "贵阳市", "贵阳", "贵州"),
    ("LS", "拉萨市", "拉萨", "西藏"),
    ("LZH", "兰州市", "兰州", "甘肃"),
    ("XN", "西宁市", "西宁", "青海"),
    ("YC", "银川市", "银川", "宁夏"),
    ("WLMQ", "乌鲁木齐市", "乌鲁木齐", "新疆"),
    ("DL", "大连市", "大连", "辽宁"),
    ("XM", "厦门市", "厦门", "福建"),
    ("BJ", "北京市", "北京", "北京"),
    ("TJ", "天津市", "天津", "天津"),
    ("SH", "上海市", "上海", "上海"),
]

# ★ 2026-10-16 升级为「全域 8 域」口径（见 docs/reports/82-）：
#   就业创业 / 企业用工 / 落户通道 / 普惠税费 / 科技企业 / 技能培训 / 人才安居 / 人才引进。
#
# 历史（为什么改）：本常量原为「最小集」5 域，且**不含** `vocational_training` ⇒
#   新城的域声明从一开始就漏培训，两度造成「数据在库里、使用者在界面上选不到」
#   （2026-10 两次扩城时暴露）。根因不在某座城漏声明，而在**模板口径过窄**。
#   ⇒ 修法 = 把模板提到全域，并且「域声明」不再当数据判据（前端下拉已改数据驱动，见 82- §4）。
#
# ★ 地域专属域（`gba_tax` 大湾区境外人才个税）**不在**默认值里 ——
#   它有明文地域限制（仅大湾区 9 市），硬铺到内陆会产出不存在的数据。
#   大湾区城市由 `--city gba_tax` 单独声明。
DOMAINS = ["employment_startup", "enterprise_support", "hukou",
           "inclusive_tax", "tech_enterprise", "vocational_training",
           "housing", "overseas"]

# 地域专属域 → 允许声明的城市码白名单（空集则全禁）。
# ★ 与「全域 8 域」互补：DOMAINS 是所有城都该有的，EXCLUSIVE_DOMAINS 只给特定城。
EXCLUSIVE_DOMAINS = {
    "gba_tax": ["GZ", "SZ", "ZH", "FS", "HZ", "DG", "ZS", "JM", "ZQ"],
}


def allowed_domains(city, base=None, exclusive=None):
    """该城**应声明**的域清单（规范序）。★ 纯函数，域清单判据的唯一实现。

    规范序 = `DOMAINS` 原序 + 该城适用的专属域（按 `EXCLUSIVE_DOMAINS` 键序追加）。
    `sync_city_domains.py` 与 `tests/test_domain_coverage.py` 都从这里取，杜绝两套判据。
    """
    base = DOMAINS if base is None else base
    exclusive = EXCLUSIVE_DOMAINS if exclusive is None else exclusive
    out = list(base)
    for d, cities in exclusive.items():
        if city in cities and d not in out:
            out.append(d)
    return out


def norm_domains(city, existing, base=None, exclusive=None):
    """把某城的域声明规范化；**越界即抛错**（绝不静默删域）。

    越界有两种，都必须炸（§5 «禁止静默降级»）：
      a) 声明了既不在 `DOMAINS` 也不在 `EXCLUSIVE_DOMAINS` 的域 —— 成分不明；
      b) 声明了专属域、但该城**不在**该专属域的白名单里 —— 错铺风险。
    """
    base = DOMAINS if base is None else base
    exclusive = EXCLUSIVE_DOMAINS if exclusive is None else exclusive
    known = set(base) | set(exclusive)
    unknown = [d for d in existing if d not in known]
    if unknown:
        raise ValueError("[%s] 声明了白名单外的域 %s ⇒ 拒绝自动处理，请人工确认"
                         % (city, unknown))
    bad = [d for d in existing if d in exclusive and city not in exclusive[d]]
    if bad:
        raise ValueError("[%s] 声明了不适用本城的专属域 %s" % (city, bad))
    return allowed_domains(city, base, exclusive)

report = []


def rd(p):
    return io.open(p, "rb").read().decode("utf-8")


def wr(p, txt):
    if APPLY:
        with io.open(p, "wb") as f:
            f.write(txt.encode("utf-8"))


# ---------------- 0) 通用文本手术（纯函数） ----------------
def _nl(txt):
    """文件自己的换行风格 —— ★ 绝不硬编码。"""
    return "\r\n" if "\r\n" in txt else "\n"


def _insert_before_close(txt, block_start, ins):
    """把 `ins`（含前导逗号）插到 `block_start` 起第一个 `}` **之前的最后一个非空白字符之后**。

    ★ 插在「最后一个非空白字符之后」而不是「`}` 之前」，是刻意的：
      后者会把收尾 `}` 粘到最后一条同一行（`"温州"  },`），格式脏且看不出是机器改的。
    """
    j = txt.index("}", block_start)
    k = j
    while k > block_start and txt[k - 1] in " \t\r\n":
        k -= 1
    if txt[k - 1] == "{":
        # 空块 `{}` —— 前导逗号会造出 `{,` 这种非法 JSON，去掉
        ins = ins.lstrip(",")
    return txt[:k] + ins + txt[k:]


# ---------------- 1) schema.json ----------------
def render_schema(txt, news=None):
    """纯函数：返回 (新文本, 报告行)。★ 不碰盘 —— 判据才能喂合成样本自检。"""
    news = NEW if news is None else news
    s = json.loads(txt)
    have = list(s["city_code"])
    todo = [(c, n) for c, n, _, _ in news if c not in set(have)]
    if not todo:
        return txt, ("city_code", "已全部存在，跳过")
    i = txt.index('"city_code": {')
    ins = "".join(',%s    "%s": "%s"' % (_nl(txt), c, n) for c, n in todo)
    new = _insert_before_close(txt, i, ins)
    chk = json.loads(new)                  # 语法必过
    assert len(chk["city_code"]) == len(have) + len(todo), "city_code 条数不符"
    assert list(chk["city_code"])[:len(have)] == have, "原有键序被改"
    return new, ("city_code", "%d → %d 键（+%s）"
                 % (len(have), len(chk["city_code"]), ",".join(c for c, _ in todo)))


def patch_schema():
    new, line = render_schema(rd(SCHEMA))
    wr(SCHEMA, new)
    report.append(("schema.json",) + line)


# ---------------- 2) HTML 三处 ----------------
def _grab_json(txt, anchor):
    """从 anchor 之后的第一个 `{` 起用 raw_decode 解析出对象。

    ★ 不找 `};` 作结束锚点：JSON 内容里的字符串可能含分号，找第一个 `};` 会截错。
    """
    i = txt.index(anchor) + len(anchor)
    i = txt.index("{", i)
    obj, _end = json.JSONDecoder().raw_decode(txt, i)
    return obj


def _city_fields_of(txt):
    """从 HTML 文本里抽 `const CITY_FIELDS={...}`（纯文本锚点，不依赖 AST）。"""
    return _grab_json(txt, "const CITY_FIELDS=")


def read_field_tpl(path):
    """从 HTML 抽统一字段模板 `const FIELD_TPL={...}`（本仓不带城市数据时的字段来源）。"""
    return _grab_json(rd(path), "const FIELD_TPL=")


def read_city_fields(path):
    return _city_fields_of(rd(path))


def build_fields_entry():
    """新城 CITY_FIELDS：取现有全城字段并集，保证无字段不可达。"""
    cf = read_city_fields(HTMLS[0])
    if not cf:
        # ★ 本仓默认 CITY_FIELDS 为空（不带城市数据）⇒ 并集会全空，
        #   新登记的城市字段一个都不可达。改用统一模板 FIELD_TPL。
        cf = {"_tpl": read_field_tpl(HTMLS[0])}
    union = {"person": set(), "entrepreneur": set(), "unit": set()}
    for v in cf.values():
        for k in union:
            union[k] |= set(v.get("fields", {}).get(k, []))
    return {"domains": DOMAINS,
            "fields": {k: sorted(union[k]) for k in ("person", "entrepreneur", "unit")}}


def render_html(txt, entry, news=None, known=None):
    """纯函数：返回 (新文本, 报告行)。★ 不碰盘 —— 判据才能喂合成样本自检。

    ★ 锚点一律锚在**对象字面量本身**（`CITY_NAMES={` / `const CITY_FIELDS=` /
      `var order=["SZ"…];`），**绝不锚「队尾是谁」** —— 旧实现锚 `QZ:"钦州"}` 就是这么烂掉的。
    """
    news = NEW if news is None else news
    cf = _city_fields_of(txt)
    # ★ 本仓 CITY_FIELDS 默认是空表 = 「所有城市都继承 FIELD_TPL」。
    #   此时不能把 news 全当成待插入项（否则跑一次就把已登记的城重新塞一遍），
    #   已在 schema 登记的城市码直接跳过。
    known = set(known or ())
    todo = [x for x in news if x[0] not in cf and x[0] not in known]
    if not todo:
        return txt, ("全部", "已全部存在，跳过")

    # a) CITY_NAMES
    pre_n = "CITY_NAMES={"
    i_n = txt.index(pre_n) + len(pre_n)
    add = "".join(',%s:"%s"' % (c, s) for c, _, s, _ in todo)
    txt = _insert_before_close(txt, i_n, add)

    # b) CITY_FIELDS —— 插在对象收尾 '}' 之前
    pre = "const CITY_FIELDS="
    i = txt.index(pre)
    i2 = txt.index("{", i)                   # 外层 `{`
    _obj, end = json.JSONDecoder().raw_decode(txt, i2)   # end = 外层 `}` 之后
    j = txt.index(";", end) + 1              # j 指向 ';' 之后
    assert txt[i2] == "{" and txt[end - 1] == "}", "CITY_FIELDS 结构不符预期"
    inner = txt[i2 + 1:end - 1]              # 去掉外层 { 与 }
    ent = json.dumps({c: entry for c, _, _, _ in todo},
                     ensure_ascii=False, separators=(",", ":"))[1:-1]
    if inner.strip():
        assert inner.rstrip().endswith("}"), "内层收尾异常"
        merged = inner.rstrip() + "," + ent
    else:
        merged = ent                         # 空表：不带前导逗号
    txt = txt[:i] + pre + "{" + merged + "};" + txt[j:]

    # c) order ×2（均为 var order=[...]）—— 两处都补
    def add_order(mo):
        return mo.group(0)[:-2] + "".join(',"%s"' % c for c, _, _, _ in todo) + "];"
    txt, cnt = re.subn(r'var order=\["SZ"[^\]]*\];', add_order, txt)
    # ★ 2026-10-22：城市清单改为完全由 /meta 驱动，静态 order 兜底已从前端移除。
    #   旧版前端能找到就补，找不到不再算错（否则本脚本对新前端直接不可用）。

    # 语法自检 —— 不论 dry-run 还是 --apply 都跑（dry-run 也得证明「改得出来」）
    chk = _city_fields_of(txt)
    assert len(chk) == len(cf) + len(todo), "CITY_FIELDS 条数不符"
    assert all(c in chk for c, _, _, _ in todo), "新城未写入"
    return txt, ("CITY_NAMES/CITY_FIELDS/order", "3 类各 1 处 + order %d 处" % cnt)


def patch_html(path, entry, known=None):
    txt, line = render_html(rd(path), entry, known=known)
    wr(path, txt)
    report.append((os.path.basename(path),) + line)


def _insert_block(txt, block, ins):
    """把 `ins`（含前导逗号）插到 `"block": { ... }` 收尾 `}` 之前（文本手术，保键序）。"""
    return _insert_before_close(txt, txt.index('"%s": {' % block), ins)


# ---------------- 3) enum_map.json ----------------
def render_enum(txt, news=None):
    """纯函数：返回 (新文本, 报告行)。

    ★ 2026-10-12 新增这一步：原脚本只写 schema + 前端 —— 而 `M.city()` / `M.province()` /
      `geo.covered_codes()` / `cross_city.scope_of()` **全读 enum_map**。
      缺这一步 → 「schema 在册」被误判成「注册完成」，新城的省份列空白、覆盖率**反向少报**，
      且是客户可见字段。受 `tests/test_city_code_consistency.py`（K1–K3）守。
    """
    news = NEW if news is None else news
    s = json.loads(txt)
    have_city = set(s.get("city") or {})
    have_prov = set(s.get("province") or {})
    todo_city = [x for x in news if x[0] not in have_city]
    todo_prov = [x for x in news if x[0] not in have_prov]
    if not todo_city and not todo_prov:
        return txt, ("city/province", "已全部存在，跳过")
    n0, n1 = len(have_city), len(have_prov)
    nl = _nl(txt)
    if todo_city:
        ins = "".join(',%s    "%s": "%s"' % (nl, c, s_) for c, _, s_, _ in todo_city)
        txt = _insert_block(txt, "city", ins)
    if todo_prov:
        ins = "".join(',%s    "%s": "%s"' % (nl, c, p) for c, _, _, p in todo_prov)
        txt = _insert_block(txt, "province", ins)
    chk = json.loads(txt)                                  # 语法必过
    assert len(chk["city"]) == n0 + len(todo_city), "city 条数不符"
    assert len(chk["province"]) == n1 + len(todo_prov), "province 条数不符"
    assert all(c in chk["city"] for c, _, _, _ in news), "新城未写入 city"
    assert all(c in chk["province"] for c, _, _, _ in news), "新城未写入 province"
    added = sorted({x[0] for x in todo_city} | {x[0] for x in todo_prov})
    return txt, ("city/province", "city %d→%d ｜ province %d→%d ｜ +%s"
                 % (n0, len(chk["city"]), n1, len(chk["province"]), ",".join(added)))


def patch_enum_map():
    new, line = render_enum(rd(ENUM))
    wr(ENUM, new)
    report.append(("enum_map.json",) + line)


if __name__ == "__main__":
    entry = build_fields_entry()
    print("[新城字段池] person=%d entrepreneur=%d unit=%d domains=%d"
          % (len(entry["fields"]["person"]), len(entry["fields"]["entrepreneur"]),
             len(entry["fields"]["unit"]), len(entry["domains"])))
    known = set(json.loads(rd(SCHEMA))["city_code"])   # 插入前先取，patch_schema 之后会多出新城
    patch_schema()
    patch_enum_map()
    for h in HTMLS:
        patch_html(h, entry, known)
    print("\n=== %s ===" % ("已写入" if APPLY else "DRY-RUN（未写盘）"))
    for a, b, c in report:
        print("  %-22s %-28s %s" % (a, b, c))
