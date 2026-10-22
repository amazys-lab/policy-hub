# -*- coding: utf-8 -*-
"""专题包构建/校验：保证 topics.json 里每个 policy_id 都真实存在于 domains，杜绝跨域引用悬空。"""
import json, io, os, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOM = os.path.join(ROOT, "policy_hub", "domains")
TOPICS = os.path.join(ROOT, "policy_hub", "topics", "topics.json")


def all_policy_ids():
    ids = {}
    for f in glob.glob(os.path.join(DOM, "*", "*.json")):
        d = json.load(io.open(f, encoding="utf-8"))
        for key in ("programs", "channels"):
            for x in d.get(key, []) or []:
                if x.get("id"):
                    ids[x["id"]] = x.get("name", "")
    return ids


def main():
    ids = all_policy_ids()
    tp = json.load(io.open(TOPICS, encoding="utf-8"))
    errors, used = [], {}
    for t in tp["topics"]:
        miss = [i for i in t["policy_ids"] if i not in ids]
        if miss:
            errors.append("%s 悬空ID %s" % (t["key"], miss))
        for i in t["policy_ids"]:
            used[i] = used.get(i, 0) + 1
        print("包 %-22s %2d 条 %s" % (t["key"], len(t["policy_ids"]), t["name"]))
    if errors:
        for e in errors:
            print("[ERROR]", e)
        sys.exit(1)
    multi = {k: v for k, v in used.items() if v > 1}
    print("专题包校验通过：共%d包，引用%d条，去重政策%d条，被多包复用%s"
          % (len(tp["topics"]), sum(len(t["policy_ids"]) for t in tp["topics"]), len(used), multi))


if __name__ == "__main__":
    main()
