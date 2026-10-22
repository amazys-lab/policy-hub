# -*- coding: utf-8 -*-
"""policy.db 哈希链自检（数据确权用）。

用法：
    python -m server.verify_db

输出三件事：
  1. 逐版重算 payload_digest，与入库时记录的值比对 —— 抓「内容被改」
  2. 检查 prev_digest 是否指向上一版 —— 抓「版本被删/链被断」
  3. 打印 chain_digest（全链指纹）—— 与 git commit message 里记录的值对照，
     两者不符即说明整条链被重写过（DB 内部自洽也躲不过这一步）

退出码：0 = 链完整；1 = 发现问题或库缺失。
"""
import os, sys, sqlite3

from .publish_db import DB, verify_chain, chain_digest, audit_anchor_coverage

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    if not os.path.exists(DB):
        print("未找到 policy.db：%s" % DB)
        print("请先运行：python -m server.publish_db \"<版本备注>\"")
        return 1
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    total = cur.execute("SELECT COUNT(*) FROM versions").fetchone()[0]
    hashed = cur.execute(
        "SELECT COUNT(*) FROM versions WHERE payload_digest IS NOT NULL").fetchone()[0]
    filed = cur.execute(
        "SELECT COUNT(*) FROM versions WHERE file_digest IS NOT NULL").fetchone()[0]
    ok, issues = verify_chain(cur)
    cd = chain_digest(cur)
    conn.close()

    # 确权锚点覆盖率（C5）：服务端读到的 JSON 是否都在 domains/**/*.json 锚点内
    cov_n, _cov, _decl, uncovered = audit_anchor_coverage()

    print("库文件        : %s" % DB)
    print("版本总数      : %d 版（有内容指纹 %d / 有文件指纹 %d）" % (total, hashed, filed))
    print("链校验通过    : %d 版" % ok)
    print("发现问题      : %d 条" % len(issues))
    for x in issues:
        print("   ! %s" % x)
    print("确权锚点覆盖  : domains/**/*.json = %d 个文件；未声明缺口 %d 个" % (cov_n, len(uncovered)))
    for r in uncovered:
        print("   ! 缺口 %s" % r)
    print("chain_digest  : %s" % cd)
    print()
    if issues:
        print("结论：数据被改动或链已断裂 —— 请对照 git commit message 中记录的 chain_digest 排查")
        return 1
    print("结论：哈希链完整，未发现篡改痕迹")
    return 0


if __name__ == "__main__":
    sys.exit(main())
