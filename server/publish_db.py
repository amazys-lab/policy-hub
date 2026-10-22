# -*- coding: utf-8 -*-
"""
数据发布脚本（版本化入库，支持多城市）
------------------------------------------------------------------
把"人工审核后的发布区"写进 SQLite(policy.db)：
  versions  每个发布版本一行（版本号/发布时间/三域条数）
  policies  每版本每条政策的完整JSON快照（线上只读这张表，可回溯任意历史版本；
            每条 payload 自带 city 字段，多城市靠它区分）

数据来源 = 顶层旧版文件 + 城市目录：
  顶层旧版：policy_hub/domains/<域>/programs.json|channels.json （有则包含，兼容旧库）
  城市目录：policy_hub/domains/cities/<城市码小写>/<域>/programs.json|channels.json
            （加城市只需放数据文件，本脚本自动发现，无需改代码）

用法：python -m server.publish_db ["版本备注"]
每次运行产生一个新版本 data_version = vYYYYMMDD-NN；线上服务永远读最新已发布版本。
"""
import os, io, json, sqlite3, datetime, sys, glob, hashlib, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOM = os.path.join(ROOT, "policy_hub", "domains")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.db")

# 字段注入的唯一实现（与 pipeline/loader.py 共用），避免两套"读源库"读出两个版本
sys.path.insert(0, os.path.join(ROOT, "policy_hub", "common"))
import record_norm  # noqa: E402

# 顶层旧版：domains/<域>/programs.json|channels.json —— 动态发现，不硬编码域清单。
# （新增顶层域文件自动纳入；窗口/目录类第二载体如 emp_windows.json 由 server/app.py
#   运行时直读，不进 policies 表 —— 与历史行为一致。）
def _discover_base_sources():
    out = []
    for p in sorted(glob.glob(os.path.join(DOM, "*", "*.json"))):
        dom, fn = os.path.basename(os.path.dirname(p)), os.path.basename(p)
        if fn in ("programs.json", "channels.json"):
            out.append((dom, p, "channels" if fn == "channels.json" else "programs"))
    return out


BASE_SOURCES = _discover_base_sources()

# 哈希链四列（数据确权用）：文件指纹 / 内容指纹 / 上一版指纹 / 文件指纹口径
DIGEST_COLUMNS = [("file_digest", "TEXT"), ("payload_digest", "TEXT"),
                  ("prev_digest", "TEXT"), ("fd_scope", "TEXT")]

# ── 确权锚点口径（C5 修复，2026-10-08）──────────────────────────────
# file_digest 是「发布区**数据**的字节指纹」。发布区 = policy_hub/domains/。
#
# v1 口径（历史遗留）：只覆盖 load_all() 用到的 100 个归档 JSON。
#   这是**实现巧合**而非设计取舍 —— 它把 16 个客户可见文件漏在确权之外：
#     · vocational_training/catalog.json ×13（SZ 基线 1 + 12 城）
#       ← /api/v1/vt_catalog 运行时**直读并返回客户**（server/app.py）
#     · employment_startup/emp_windows.json（人社经办窗口）
#     · hukou/hukou_windows.json（户政窗口）
#     · hukou/points_cutoff.json（积分入户历年线）
#   后果：改这 16 个文件里任意一个，客户看到的内容变了，source_version 却不变。
#
# v2 口径（现行）：覆盖 domains/ 下**全部** *.json（当前 116 个）。
#   「发布区有多少数据文件，锚点就盖多少」 —— 新增文件自动纳入，无需改代码，
#   消除了「只有发版机制恰好读到的文件才算数」这个错误前提。
FD_SCOPE_V1 = "loadall-100-v1"
FD_SCOPE_V2 = "domains-json-v2"

# 锚点外但客户可见的运行时 JSON —— 显式声明，避免被当成"漏网"，
# 同时保证**新增**的域外数据源会被 audit_anchor_coverage 立刻发现。
# 这些是服务端配置 / 运行时状态，由 git commit（字节保真，见 11-确权加固报告）锚定，
# 不属于"每版发布的数据"，因此**有意**不进 file_digest。
KNOWN_OUT_OF_SCOPE = {
    "policy_hub/topics/topics.json": "专题文案（服务端配置，git commit 锚定）",
    "policy_hub/common/schema.json": "城市码 / 字段契约表（schema，git commit 锚定）",
    "policy_hub/common/field_contract.json": "字段契约派生表（由 schema 生成，git commit 锚定）",
    "server/leads.json": "用户留资（运行时状态，非政策数据）",
}

# policies 是**视图**（内容寻址：blobs 存唯一内容 + policy_refs 存引用）。
# 列名/列序与原表完全一致 → 所有历史 `SELECT ... FROM policies` 无需改动。
POLICIES_VIEW_SQL = """
CREATE VIEW policies AS
  SELECT r.data_version, r.item_id, r.domain, r.name, r.result_type, r.valid, b.payload
  FROM policy_refs r JOIN blobs b ON r.digest = b.digest
"""


def ensure_schema(cur):
    """幂等建表：versions + 内容寻址结构（blobs / policy_refs / policies 视图）。

    改成内容寻址的原因：原先每版存 816 条完整 JSON 快照，95 版 = 56,644 行 / 231 MB，
    而唯一内容只有 5,048 份 / 15.9 MB（跨版重复 91%）。
    """
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS versions(
        data_version TEXT PRIMARY KEY, published_at TEXT,
        emp_count INTEGER, hk_count INTEGER, os_count INTEGER, note TEXT);
    CREATE TABLE IF NOT EXISTS blobs(
        digest TEXT PRIMARY KEY, payload TEXT);
    CREATE TABLE IF NOT EXISTS policy_refs(
        data_version TEXT, item_id TEXT, domain TEXT, name TEXT,
        result_type TEXT, valid TEXT, digest TEXT,
        PRIMARY KEY(data_version,item_id));
    """)
    row = cur.execute("SELECT type FROM sqlite_master WHERE name='policies'").fetchone()
    if row is None:
        cur.execute(POLICIES_VIEW_SQL)
    elif row[0] != "view":
        raise RuntimeError(
            "policies 仍是「表」结构（未迁移）。请先执行：\n"
            "    python pipeline/migrate_to_blobs.py --apply")


def ensure_digest_columns(cur):
    """幂等：给 versions 补哈希链列（老库走 ALTER，新库建表后即为空列）。

    并给「已有 file_digest 但没标口径」的历史行回填 **v1 口径** —— 它们是用旧输入集
    （load_all 的 100 文件）算的。标上口径后，用现行 v2 口径复算时不会把
    「口径升级」误判成「篡改」。
    """
    have = {r[1] for r in cur.execute("PRAGMA table_info(versions)")}
    for col, typ in DIGEST_COLUMNS:
        if col not in have:
            cur.execute("ALTER TABLE versions ADD COLUMN %s %s" % (col, typ))
    cur.execute("UPDATE versions SET fd_scope=? WHERE file_digest IS NOT NULL AND fd_scope IS NULL",
                (FD_SCOPE_V1,))


def domain_json_files():
    """确权锚点输入集：发布区 `policy_hub/domains/**/*.json` **全量**（按路径排序）。

    C5 修复点：这才是 file_digest 应有的口径。原先喂 load_all() 的文件清单，
    等于"只有发版机制读的文件才算数"，把 catalog.json 这类被 API 运行时直读、
    客户可见的辅助数据排除在确权之外。改成目录全量后，加数据文件即自动纳入锚点。
    """
    return sorted(glob.glob(os.path.join(DOM, "**", "*.json"), recursive=True))


# 请求时可能读到 JSON 的代码面 —— 只审这里，避免把 staging / 报告 / 快照等非发布物算进缺口
_SERVING_GLOB = ("server", "**", "*.py")
# 字面量里含这些字符的不是"具体文件路径"（glob / 正则 / 占位符），跳过
_LIT_SKIP_CHARS = "*()|<>%"


def audit_anchor_coverage():
    """确权覆盖率审计 —— **服务端请求时读到的 JSON，是否都在确权锚点内？**

    锚点 = `domains/**/*.json` 全量；但"域内的新文件"天然被覆盖，真正的风险是
    有人在**域外**新增数据文件又被服务端读取（C5 的成因正是如此：catalog.json
    被 /api/v1/vt_catalog 直读，却不在旧锚点里）。

    做法：扫服务端源码里的 `*.json` 字面量 → 逐个判定
      · covered   —— 命中锚点（按全路径优先、否则按文件名）
      · declared  —— 命中 KNOWN_OUT_OF_SCOPE（配置/运行时状态，git 锚定）
      · uncovered —— **两者都不是 = 新的确权缺口**（非空即应阻断发版）

    返回 (锚点文件数, covered列表, declared列表, uncovered列表)。
    """
    cov_paths = domain_json_files()
    covered_rel = {os.path.relpath(p, ROOT).replace(os.sep, "/") for p in cov_paths}
    covered_names = {os.path.basename(p) for p in cov_paths}
    decl_rel = set(KNOWN_OUT_OF_SCOPE)
    decl_names = {os.path.basename(k) for k in KNOWN_OUT_OF_SCOPE}

    hits = set()
    for fp in glob.glob(os.path.join(ROOT, *_SERVING_GLOB), recursive=True):
        try:
            txt = io.open(fp, encoding="utf-8").read()
        except Exception:
            continue
        for lit in re.findall(r"""['"]([^'"\n]+\.json)['"]""", txt):
            if any(ch in lit for ch in _LIT_SKIP_CHARS) or lit.startswith("."):
                continue
            hits.add(lit.replace("\\", "/"))

    covered, declared, uncovered = [], [], []
    for lit in sorted(hits):
        if "/" in lit:
            bucket = covered if lit in covered_rel else (declared if lit in decl_rel else uncovered)
        else:
            bucket = covered if lit in covered_names else (declared if lit in decl_names else uncovered)
        bucket.append(lit)
    return len(cov_paths), covered, declared, uncovered


def file_digest(paths):
    """发布区数据字节指纹 —— 确权锚点。

    按「相对 ROOT 的 POSIX 路径」排序后，逐文件写入  路径\\0原始字节\\0  ，取 SHA-256。
    刻意不做任何规范化（CRLF 原样、JSON 不重排、空行不加不减），
    因此任何人拿着「当时那份源文件目录」都能独立复现出同一个哈希。

    输入集 = domain_json_files()（domains/**/*.json 全量，口径 FD_SCOPE_V2）。
    """
    items = sorted((os.path.relpath(p, ROOT).replace(os.sep, "/"), p) for p in paths)
    h = hashlib.sha256()
    for rel, p in items:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(io.open(p, "rb").read())
        h.update(b"\0")
    return h.hexdigest()


def payload_digest(cur, version):
    """某一版 DB 内容的指纹：按 item_id 排序拼接 (item_id, payload) 后取 SHA-256。
    该版任一行被改写或删除，这个值就会变。"""
    h = hashlib.sha256()
    for item_id, payload in cur.execute(
            "SELECT item_id,payload FROM policies WHERE data_version=? ORDER BY item_id", (version,)):
        h.update(str(item_id).encode("utf-8"))
        h.update(b"\0")
        h.update(payload.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def prev_digest(cur, version):
    """上一版的 payload_digest，形成哈希链（按发布时间，同刻取 rowid 大者）。"""
    row = cur.execute(
        "SELECT payload_digest FROM versions WHERE payload_digest IS NOT NULL AND data_version<>? "
        "ORDER BY published_at DESC, rowid DESC LIMIT 1", (version,)).fetchone()
    return (row[0] or "") if row else ""


def verify_chain(cur, strict=False):
    """校验哈希链：逐版重算 payload_digest 并比对，同时检查 prev_digest 是否指向上一版。
    返回 (通过数, 问题列表)。strict=True 时要求每版都必须有哈希（含历史版）。"""
    rows = cur.execute("SELECT rowid,data_version,published_at,payload_digest,prev_digest "
                       "FROM versions ORDER BY published_at, rowid").fetchall()
    issues, ok, prev = [], 0, None
    for _rid, ver, _at, stored, stored_prev in rows:
        if stored is None:
            if strict:
                issues.append("%s: 缺 payload_digest" % ver)
            continue
        now = payload_digest(cur, ver)
        if now != stored:
            issues.append("%s: 内容已被改动（存 %s… 实 %s…）" % (ver, stored[:12], now[:12]))
        elif (stored_prev or "") != (prev or ""):
            issues.append("%s: 链接断开（存 %s… 应为 %s…）"
                          % (ver, (stored_prev or "空")[:12], (prev or "空")[:12]))
        else:
            ok += 1
        prev = stored
    return ok, issues


def chain_digest(cur):
    """整条哈希链的单一指纹 —— 用于**外部锚定**。

    把各版 (data_version, payload_digest) 按发布时间串联后取 SHA-256。
    只需把这个值发布到 DB 之外（git commit message / 邮件发给自己 / 时间戳服务），
    即便有人把整条链重写一遍（内部自洽、verify_chain 查不出），也会与外部见证不符。
    """
    h = hashlib.sha256()
    for ver, pd in cur.execute("SELECT data_version,payload_digest FROM versions "
                               "WHERE payload_digest IS NOT NULL ORDER BY published_at, rowid"):
        h.update(ver.encode("utf-8"))
        h.update(b"\0")
        h.update((pd or "").encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def discover_city_sources():
    """自动发现新城市：domains/cities/<城市码>/<域>/(programs|channels).json"""
    found = []
    croot = os.path.join(DOM, "cities")
    if not os.path.isdir(croot):
        return found
    for citydir in sorted(glob.glob(os.path.join(croot, "*"))):
        if not os.path.isdir(citydir):
            continue
        city = os.path.basename(citydir).upper()
        for domdir in sorted(glob.glob(os.path.join(citydir, "*"))):
            if not os.path.isdir(domdir):
                continue
            dom = os.path.basename(domdir)
            for fn, lk in (("programs.json", "programs"), ("channels.json", "channels")):
                fp = os.path.join(domdir, fn)
                if os.path.exists(fp):
                    found.append((dom, fp, lk, city))
    return found


def load_all():
    """同域多城市合并到一个 list（逐条 payload.city 区分）。

    返回 (数据, 装载明细, 源文件清单, domain 不一致告警)。
    注入 city/domain 走 record_norm（与 loader.py 同一实现）—— 这是 P0-2「DB 与源库脱节」的根因修复。
    """
    out, meta, files, mism = {}, [], [], []
    warn = lambda i, a, b: mism.append((i, a, b))  # noqa: E731

    for dom, path, lk in BASE_SOURCES:
        items = json.load(io.open(path, encoding="utf-8")).get(lk, [])
        items = [record_norm.inject(it, "SZ", dom, warn) for it in items]
        out.setdefault(dom, []).extend(items)
        meta.append(("SZ", dom, len(items)))
        files.append(path)
    for dom, path, lk, city in discover_city_sources():
        items = json.load(io.open(path, encoding="utf-8")).get(lk, [])
        items = [record_norm.inject(it, city, dom, warn) for it in items]
        out.setdefault(dom, []).extend(items)
        meta.append((city, dom, len(items)))
        files.append(path)
    return out, meta, files, mism


def main():
    note = sys.argv[1] if len(sys.argv) > 1 else ""
    # --allow-uncovered：覆盖率审计发现未声明域外 JSON 时，仍继续发版（应急逃生口）
    allow_uncovered = "--allow-uncovered" in sys.argv

    # ── 发版前自检 ③（2026-10-09）：统一体检（healthcheck）───────────────
    # 起因：自检 ①② 只覆盖 city/domain 必填 + 确权覆盖率，而**闸门那些校验压根没被调用**，
    #       导致"检查清单 ≠ 实际跑的检查"——这是历次问题反复流出到客户面前的机制根因。
    # 现在把统一体检焊在发版出口：跨城域归属 / deadline 契约 / 必填空值 / 链路工具自检，
    #       覆盖全字段·全域·全记录；已确认的存量问题记在
    #       policy_hub/common/known_issues.json → 只拦【新增】。
    # 逃生口：--skip-healthcheck（应急用，须在版本备注写明原因）。
    if "--skip-healthcheck" not in sys.argv:
        import subprocess
        hc = subprocess.run([sys.executable, "-m", "policy_hub.collector.healthcheck"],
                            cwd=ROOT, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
        print(hc.stdout.rstrip())
        if hc.stderr:
            print(hc.stderr.rstrip())
        if hc.returncode != 0:
            print("!! 统一体检未通过（exit %d）→ 发版中止。" % hc.returncode)
            print("   → 修完重跑；确需应急可加 --skip-healthcheck，并在版本备注写明原因。")
            sys.exit(3)

    data, meta, files, mism = load_all()

    # 发版前自检 ①：city/domain 必须齐全（否则线上列表无法归属城市）
    all_recs = [it for items in data.values() for it in items]
    bad = record_norm.check_required(all_recs)
    if bad:
        print("!! 发版中止：以下记录缺 city/domain ——")
        for i, why in bad[:20]:
            print("   ", i, why)
        print("  共 %d 条" % len(bad))
        sys.exit(1)
    if mism:
        print("!! domain 与所在目录不一致（以目录为准，请人工复核）%d 条：" % len(mism))
        for i, a, b in mism[:10]:
            print("   ", i, "记录=%r 目录=%r" % (a, b))

    # 发版前自检 ②（C5）：确权锚点覆盖率 —— 服务端读到的 JSON 有没有落在锚点之外
    cov_n, _cov_hits, declared, uncovered = audit_anchor_coverage()
    if uncovered:
        print("!! 确权锚点缺口：以下 JSON 被服务端读取，但既不在 domains/ 锚点内，也未声明 ——")
        for r in uncovered:
            print("   ", r)
        print("   它们若被改动，file_digest 不会变（客户可见内容却变了）。")
        if not allow_uncovered:
            print("   → 发版中止。确认无误后加 --allow-uncovered，或补进 KNOWN_OUT_OF_SCOPE。")
            sys.exit(2)

    today = datetime.date.today().isoformat().replace("-", "")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    ensure_schema(cur)
    ensure_digest_columns(cur)
    n = cur.execute("SELECT COUNT(*) FROM versions WHERE data_version LIKE ?", ("v" + today + "-%",)).fetchone()[0]
    version = "v%s-%02d" % (today, n + 1)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    counts = {}
    for dom, items in data.items():
        counts[dom] = len(items)
        for it in items:
            payload = json.dumps(it, ensure_ascii=False)
            dg = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            cur.execute("INSERT OR IGNORE INTO blobs(digest,payload) VALUES(?,?)", (dg, payload))
            cur.execute("INSERT OR REPLACE INTO policy_refs VALUES(?,?,?,?,?,?,?)",
                        (version, it.get("id", "?"), dom, it.get("name", ""),
                         it.get("result_type", ""), it.get("valid", "active"), dg))
    # 回收孤儿内容：任何版本都不再引用的 payload（内容寻址的天然副产品）
    cur.execute("DELETE FROM blobs WHERE digest NOT IN (SELECT DISTINCT digest FROM policy_refs)")
    # 哈希链：写入本版内容指纹 + 发布区数据指纹（口径 v2 = domains 全量），并链接上一版
    pd = payload_digest(cur, version)
    pv = prev_digest(cur, version)
    fd = file_digest(domain_json_files())
    cur.execute(
        "INSERT INTO versions(data_version,published_at,emp_count,hk_count,os_count,note,"
        "file_digest,payload_digest,prev_digest,fd_scope) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (version, now, counts.get("employment_startup", 0),
         counts.get("hukou", 0), counts.get("overseas", 0), note, fd, pd, pv, FD_SCOPE_V2))
    conn.commit()
    rows = cur.execute("SELECT data_version,published_at,emp_count,hk_count,os_count,"
                       "substr(payload_digest,1,12) FROM versions ORDER BY data_version").fetchall()
    cd = chain_digest(cur)
    conn.close()
    print("已发布新版本:", version, counts, (("备注:" + note) if note else ""))
    print("  file_digest    (发布区数据) =", fd, "[口径 %s]" % FD_SCOPE_V2)
    print("  payload_digest (本版内容) =", pd)
    print("  prev_digest    (上一版)   =", pv or "(首版)")
    print("  chain_digest   (全链)     =", cd, " <- 建议抄进 git commit / 邮件自存")
    print("确权锚点覆盖  domains/**/*.json = %d 个文件（域外已声明 %d 个）" % (cov_n, len(declared)))
    print("本次装载明细(城市/域/条数):")
    for city, dom, c in meta:
        print("   ", city, dom, c)
    print("历史版本:")
    for r in rows:
        print("  ", r)


if __name__ == "__main__":
    main()
