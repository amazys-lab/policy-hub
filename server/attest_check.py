# -*- coding: utf-8 -*-
"""确权锚点自检（C5 修复配套工具）。

用法：
    python -m server.attest_check            # 只读自检
    python -m server.attest_check --diff-git # 指纹不一致时，顺带列出 domains 的未提交改动

回答三个问题：
  ① 覆盖率 —— 服务端请求时读到的 JSON，是否都在确权锚点（domains/**/*.json）内？
     （C5 缺口就是"读得到、但锚不到"；本项非空即说明缺口复现）
  ② 同步性 —— 当前发布区数据的字节指纹，是否等于**最新已发布版本**记录的 file_digest？
     不等 = 发布区改了但还没发版（或有人绕过发版直接改了数据）。
  ③ 口径   —— 最新版记录的 fd_scope 是否与现行口径一致（口径升级不算篡改）。

退出码：0 = 全绿；1 = 发现缺口 / 指纹不一致；2 = 库或数据缺失。
"""
import os, sys, sqlite3

from .publish_db import (DB, ROOT, FD_SCOPE_V2, domain_json_files, file_digest,
                         audit_anchor_coverage, chain_digest)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _git_dirty_domains():
    """列出 domains/ 下相对最后一次提交有改动的文件（定位指纹差异来源）。"""
    import subprocess
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", "policy_hub/domains"],
                             cwd=ROOT, capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def main():
    diff_git = "--diff-git" in sys.argv
    if not os.path.isdir(os.path.join(ROOT, "policy_hub", "domains")):
        print("未找到发布区：%s/policy_hub/domains" % ROOT)
        return 2

    cov_n, covered, declared, uncovered = audit_anchor_coverage()
    cur_fd = file_digest(domain_json_files())

    print("确权锚点自检")
    print("  仓库根        : %s" % ROOT)
    print("  锚点口径      : %s" % FD_SCOPE_V2)
    print("  锚点文件数    : %d 个  (policy_hub/domains/**/*.json)" % cov_n)
    print("  当前源库指纹  : %s" % cur_fd)
    print()
    print("① 覆盖率审计（服务端读到的 JSON 是否都在锚点内）")
    print("    命中锚点 : %d  %s" % (len(covered), covered))
    print("    域外声明 : %d  %s" % (len(declared), declared))
    print("    未声明缺口: %d  %s" % (len(uncovered), uncovered))

    rc = 0
    if uncovered:
        print("    ! 锚点缺口复现：这些文件被服务端读取却不在锚点内 —— 改动不会被 file_digest 察觉")
        rc = 1

    print()
    print("② 同步性（当前源库 vs 最新已发布版本）")
    if not os.path.exists(DB):
        print("    ! 未找到 policy.db，跳过（先运行 python -m server.publish_db）")
        return 2
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    row = cur.execute("SELECT data_version,published_at,file_digest,fd_scope FROM versions "
                      "ORDER BY published_at DESC, rowid DESC LIMIT 1").fetchone()
    cd = chain_digest(cur)
    conn.close()
    if not row:
        print("    ! versions 表为空")
        return 2
    ver, at, stored_fd, scope = row
    print("    最新版本   : %s  发布时间 %s" % (ver, at))
    print("    记录指纹   : %s  [口径 %s]" % (stored_fd or "(无)", scope or "(未标)"))
    print("    当前指纹   : %s  [口径 %s]" % (cur_fd, FD_SCOPE_V2))
    if not stored_fd:
        print("    · 该版无 file_digest（确权加固前发布），无法比对")
    elif scope != FD_SCOPE_V2:
        print("    · 口径不同（历史版为 %s），不做等值比对 —— 口径升级不算篡改" % (scope or "未标"))
    elif stored_fd == cur_fd:
        print("    结论       : ✅ 一致 —— 发布区与最新发布版同步")
    else:
        print("    结论       : ⚠️ 不一致 —— 发布区已改但未发新版，或有人绕过发版改了数据")
        rc = 1
        if diff_git:
            dirty = _git_dirty_domains()
            print("    domains 未提交改动（%d）：" % len(dirty))
            for ln in dirty[:40]:
                print("      %s" % ln)

    print()
    print("    chain_digest : %s" % cd)
    print("    （与 git commit message 中记录的值对照；不符即整链被重写过）")
    print()
    print("结论：%s" % ("✅ 全绿" if rc == 0 else "⚠️ 有待处理项"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
