# -*- coding: utf-8 -*-
"""存量城市的「域声明」同步到全域口径（2026-10-16 建，配套 `82-全域采集口径`）。

## 为什么需要它

`register_city_codes.DOMAINS` 只决定**新城**注册时的域名声明，**改不了存量**。
而口径从「最小集 5 域」升到「全域 8 域」后，存量 51 城里：

    · 多数城只声明 5~6 域（缺技能培训 / 人才安居 / 人才引进）
    · 少数城声明 7 域（缺 人才安居 / 人才引进）
    · 个别城域清单**顺序混乱**（历史遗留）
    · 采集最全的城声明 9 域

本工具把它们一次性补齐到规范序。

## 三条铁律

1. **绝不删域** —— `existing` 里出现白名单外的域 ⇒ **抛错**，拒绝静默丢弃
   （§5 «禁止静默降级»：宁可炸，不可悄悄少一个域）。
2. **专属域有白名单** —— `gba_tax`（大湾区境外人才个税，明文地域限制）
   只许珠三角 9 市声明 ⇒ 防「异地硬套产出错数据」。
3. **判据不重复** —— 域清单唯一真值源 = `register_city_codes.DOMAINS`
   （+ `EXCLUSIVE_DOMAINS`），本文件不另抄一份。

★ 判据内核纯函数化：`norm_domains()` / `render_sync()` 只吃数据、只吐数据，
  不碰盘 ⇒ 正例与反例能共用同一实现（§5i：修复会过期，断言是永久）。

用法：
    python sync_city_domains.py            # dry-run（只打印差异）
    python sync_city_domains.py --apply    # 落盘 + 语法自检
"""
import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import register_city_codes as RCC      # noqa: E402  （顶层无 I/O 副作用）

HTMLS = [os.path.join(ROOT, "server", "static", "client.html"),
         os.path.join(ROOT, "server", "static", "demo_api.html")]


# ---------------- 判据内核（★ 唯一实现 = register_city_codes） ----------------
# `allowed_domains()` / `norm_domains()` 定义在 `register_city_codes.py` ——
# 那里是域清单的真值源（`DOMAINS` / `EXCLUSIVE_DOMAINS` 的所在地）。
# 本文件与 `tests/test_domain_coverage.py` 都从那里取，杜绝「一处需求两套改法」。
norm_domains = RCC.norm_domains


def render_sync(txt, base=None, exclusive=None):
    """纯函数：HTML 文本 → (新文本, {城: (旧域, 新域)})。★ 不碰盘。"""
    cf = RCC._city_fields_of(txt)
    changed = {}
    for c in list(cf):
        old = list(cf[c].get("domains") or [])
        new = norm_domains(c, old, base, exclusive)
        if new != old:
            changed[c] = (old, new)
            cf[c]["domains"] = new
    if not changed:
        return txt, changed
    i = txt.index("const CITY_FIELDS={")
    j = txt.index("};", i) + 2
    body = ("const CITY_FIELDS="
            + json.dumps(cf, ensure_ascii=False, separators=(",", ":")) + ";")
    return txt[:i] + body + txt[j:], changed


# ---------------- 主流程 ----------------
def main(argv):
    apply = "--apply" in argv
    all_changed = {}
    new_texts = {}
    for p in HTMLS:
        raw = io.open(p, "rb").read().decode("utf-8")
        txt, changed = render_sync(raw)
        name = os.path.basename(p)
        new_texts[p] = (txt, raw)
        all_changed[name] = changed

        # 语法自检（dry-run 也跑 —— 证明「改得出来」）
        cf = RCC._city_fields_of(txt)
        for c, (old, new) in changed.items():
            assert cf[c]["domains"] == new, "写入校验失败：%s %s" % (name, c)
        print("[%s] 变更 %d 城 / 城数 %d" % (name, len(changed), len(cf)))

    # 变更明细（任一份的并集，两份必须同源）
    if all_changed["client.html"] != all_changed["demo_api.html"]:
        raise AssertionError("两份 HTML 的变更集不一致 ⇒ 先修分叉（见 82- §4）")
    for c in sorted(all_changed["client.html"]):
        old, new = all_changed["client.html"][c]
        print("   %-4s %-2d→%-2d  +%s" % (c, len(old), len(new),
                                          ",".join(d for d in new if d not in old)))

    # 域分布自检
    import collections
    cf = RCC._city_fields_of(new_texts[HTMLS[0]][0])
    dist = collections.Counter(len(v.get("domains") or []) for v in cf.values())
    print("\n改后域数分布：", dict(sorted(dist.items())))
    print("  8 域城数 %d（应 42）｜9 域城数 %d（应 9，珠三角）"
          % (dist.get(8, 0), dist.get(9, 0)))

    if not apply:
        print("\n[dry-run] 未落盘。加 --apply 执行。")
        return 0

    for p, (txt, raw) in new_texts.items():
        if txt != raw:
            with io.open(p, "wb") as f:
                f.write(txt.encode("utf-8"))
            print("[落盘] %s" % os.path.basename(p))
    print("\n★ 下一步：node pipeline/extract_frontend.js  （派生物必须派生）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
