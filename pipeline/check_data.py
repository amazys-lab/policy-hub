# -*- coding: utf-8 -*-
"""数据自检：检查 policy_hub/domains/ 下填进去的条目是否符合字段契约。

本仓不附带政策数据，这个脚本是「填完之后先自己查一遍」的那一步 ——
不联网、不写盘，只做结构判定。链接能不能打开不在这里管（那是 link_guard 的事）。

用法：
    python pipeline/check_data.py              # 查全部
    python pipeline/check_data.py --city SZ    # 只查一座城
    python pipeline/check_data.py -q           # 只打汇总，不逐条列

退出码：0 = 通过（空库也算通过）；1 = 有问题。
"""
import io
import json
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CITIES_DIR = os.path.join(ROOT, "policy_hub", "domains", "cities")
SCHEMA = os.path.join(ROOT, "policy_hub", "common", "schema.json")
ENUM = os.path.join(ROOT, "pipeline", "enum_map.json")

# 政策条目的必填字段（与 templates/new_city/programs.template.json 的 _填写说明 一致）
# ★ 不含 materials / guide_url：这两项允许留空（材料还没整理、已废止的记录没有线上入口），
#   留空只在汇总里提一句，不算错 —— 强行必填会逼人填假值。
PROGRAM_REQUIRED = ["id", "city", "domain", "name", "valid", "result_type", "depth",
                    "cond", "amount", "version", "updated_at", "source_doc"]
# 通道条目字段少得多：一条通道可以没有金额，但必须有 ID、名称与判定条件
CHANNEL_REQUIRED = ["id", "city", "name", "valid", "cond"]

ID_RE = re.compile(r"^([A-Z]{2,4})-([A-Z]{2,4})-(\d{3})$")
URL_FIELDS = ("guide_url", "apply_url", "url", "entry_url")


def rd(p):
    return json.loads(io.open(p, "rb").read().decode("utf-8"))


def walk(city_filter=None):
    """遍历 cities/<城码小写>/<域>/*.json，产出 (路径, 城市码, 域名, 数据)。"""
    if not os.path.isdir(CITIES_DIR):
        return
    for city in sorted(os.listdir(CITIES_DIR)):
        d = os.path.join(CITIES_DIR, city)
        if not os.path.isdir(d):
            continue
        if city_filter and city.upper() != city_filter.upper():
            continue
        for dom in sorted(os.listdir(d)):
            dd = os.path.join(d, dom)
            if not os.path.isdir(dd):
                continue
            for fn in sorted(os.listdir(dd)):
                if not fn.endswith(".json"):
                    continue
                p = os.path.join(dd, fn)
                try:
                    data = rd(p)
                except Exception as e:
                    yield p, city.upper(), dom, {"__parse_error__": str(e)}
                    continue
                yield p, city.upper(), dom, data


def check_file(path, city, dom, data, codes, valid_enum, errors, warns):
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    if "__parse_error__" in data:
        errors.append("%s  JSON 解析失败：%s" % (rel, data["__parse_error__"]))
        return 0

    if not isinstance(data, dict):
        errors.append("%s  顶层应为对象（含 programs 或 channels 数组）" % rel)
        return 0

    key = "programs" if "programs" in data else ("channels" if "channels" in data else None)
    if key is None:
        errors.append("%s  缺 programs 或 channels 数组" % rel)
        return 0
    items = data.get(key)
    if not isinstance(items, list):
        errors.append("%s  %s 应为数组" % (rel, key))
        return 0

    required = PROGRAM_REQUIRED if key == "programs" else CHANNEL_REQUIRED
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errors.append("%s  %s[%d] 不是对象" % (rel, key, i))
            continue
        pid = it.get("id") or "%s[%d]" % (key, i)
        where = "%s  %s" % (rel, pid)

        # 1) 必填
        miss = [k for k in required if it.get(k) in (None, "")]
        if miss:
            errors.append("%s  缺必填字段 %s" % (where, ", ".join(miss)))

        # 2) ID 形态 + 城市前缀 + 与目录一致
        m = ID_RE.match(str(it.get("id") or ""))
        if it.get("id") and not m:
            errors.append("%s  ID 形态不对（应形如 XX-EMP-001）" % where)
        elif m:
            pre = m.group(1)
            if pre not in codes:
                errors.append("%s  ID 城市码 %s 未在 schema.city_code 登记" % (where, pre))
            if pre != city:
                errors.append("%s  ID 城市码 %s 与目录 %s 不一致" % (where, pre, city))

        # 3) 路径与字段一致
        if it.get("city") and str(it["city"]).upper() != city:
            errors.append("%s  city 字段 %s 与目录 %s 不一致" % (where, it["city"], city))
        if it.get("domain") and it["domain"] != dom:
            errors.append("%s  domain 字段 %s 与目录 %s 不一致" % (where, it["domain"], dom))

        # 4) 枚举
        v = it.get("valid")
        if v and valid_enum and v not in valid_enum:
            errors.append("%s  valid=%s 不在枚举内（%s）" % (where, v, "/".join(valid_enum)))
        rt = it.get("result_type")
        if rt and rt not in ("money", "channel", "review", "mixed"):
            errors.append("%s  result_type=%s 非法（money/channel/review/mixed）" % (where, rt))
        dp = it.get("depth")
        if dp and dp not in ("L1", "L2", "L3", "L4"):
            errors.append("%s  depth=%s 非法（L1~L4）" % (where, dp))

        # 5) 链接字段：空可以，非空必须是 http(s)
        for f in URL_FIELDS:
            u = it.get(f)
            if isinstance(u, str) and u.strip() and not u.strip().lower().startswith(("http://", "https://")):
                errors.append("%s  %s 不是 http(s) 链接：%s" % (where, f, u[:40]))

        # 6) 结构体字段形态：cond / amount 是对象，materials 是字符串数组
        for f in ("cond", "amount"):
            if it.get(f) is not None and not isinstance(it[f], dict):
                errors.append("%s  %s 应为对象" % (where, f))
        mat = it.get("materials")
        if mat is not None:
            if not isinstance(mat, list):
                errors.append("%s  materials 应为字符串数组" % where)
            elif any(not isinstance(x, str) for x in mat):
                errors.append("%s  materials 里混了非字符串项" % where)

        if key == "programs" and not it.get("guide_url") and not it.get("apply_url"):
            warns.append("%s  既无 guide_url 也无 apply_url（客户点不到原文）" % where)

    return len(items)


def main():
    city_filter = None
    quiet = "-q" in sys.argv or "--quiet" in sys.argv
    if "--city" in sys.argv:
        i = sys.argv.index("--city")
        if i + 1 < len(sys.argv):
            city_filter = sys.argv[i + 1]

    schema = rd(SCHEMA)
    codes = set(schema.get("city_code") or {})
    try:
        valid_enum = set((rd(ENUM).get("valid") or {}))
    except Exception:
        valid_enum = set()

    errors, warns = [], []
    files = total = 0
    seen = {}
    for path, city, dom, data in walk(city_filter):
        files += 1
        n = check_file(path, city, dom, data, codes, valid_enum, errors, warns)
        total += n
        key = "programs" if "programs" in (data or {}) else "channels"
        for it in (data.get(key) or []):
            pid = it.get("id") if isinstance(it, dict) else None
            if pid:
                if pid in seen:
                    errors.append("%s  ID 重复出现（另见 %s）"
                                  % (os.path.relpath(path, ROOT).replace("\\", "/"), seen[pid]))
                else:
                    seen[pid] = os.path.relpath(path, ROOT).replace("\\", "/")

    scope = "（只查 %s）" % city_filter.upper() if city_filter else ""
    print("检查 %d 个文件 / %d 条记录%s" % (files, total, scope))
    if not total:
        print("\n库里还没有任何条目 —— 这是本仓的默认状态，不算错。")
        print("接入方式见 policy_hub/domains/README.md。")
        print("\n通过。")
        return 0

    if not quiet:
        for e in errors:
            print("  [错误] " + e)
        for w in warns:
            print("  [提醒] " + w)
    print("\n%d 个错误 / %d 个提醒" % (len(errors), len(warns)))
    if errors:
        print("先修错误再跑引擎 —— 字段错了，后面的匹配与金额都是错的。")
        return 1
    print("通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
