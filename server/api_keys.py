# -*- coding: utf-8 -*-
"""
API Key 命令行管理（阶段B骨架）
------------------------------------------------------------------
用法（项目根目录）：
  python -m server.api_keys list                      列出全部 Key
  python -m server.api_keys create --tenant "XX财税"   签发(trial套餐)
  python -m server.api_keys create --tenant "XX园区" --plan pro
  python -m server.api_keys plan sk-xxxx pro          改套餐(trial/free/pro)
  python -m server.api_keys disable sk-xxxx           停用
  python -m server.api_keys enable sk-xxxx            重新启用
"""
import os, sys, sqlite3, secrets, argparse, datetime

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.db")
PLANS = ("trial", "free", "pro")


def conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c


def ensure():
    c = conn()
    c.execute("CREATE TABLE IF NOT EXISTS api_keys("
              "key TEXT PRIMARY KEY, tenant TEXT, plan TEXT DEFAULT 'trial',"
              "enabled INTEGER DEFAULT 1, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS usage_logs("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, ts TEXT,"
              "endpoint TEXT, status INTEGER)")
    c.commit(); return c


def do_create(a):
    if a.plan not in PLANS:
        print("套餐只能是", PLANS); sys.exit(2)
    key = "sk-" + secrets.token_hex(16)
    c = ensure()
    c.execute("INSERT INTO api_keys(key,tenant,plan,enabled,created_at) VALUES(?,?,?,1,?)",
              (key, a.tenant or "未命名", a.plan, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    c.commit(); c.close()
    print("已签发 API Key：%s" % key)
    print("租户：%s  套餐：%s" % (a.tenant, a.plan))
    print("调用示例：curl -H \"X-API-Key: %s\" http://127.0.0.1:8000/open/v1/meta" % key)


def do_list(a):
    c = ensure()
    rows = c.execute("SELECT * FROM api_keys ORDER BY created_at").fetchall(); c.close()
    if not rows:
        print("（还没有 Key，用 create 签发）"); return
    for r in rows:
        print("%s | %s | 套餐=%s | %s | 创建=%s" %
              (r["key"], r["tenant"], r["plan"], "启用" if r["enabled"] else "停用", r["created_at"]))


def _set_enabled(key, val):
    c = ensure(); cur = c.execute("UPDATE api_keys SET enabled=? WHERE key=?", (val, key))
    c.commit(); c.close()
    print(("已启用 " if val else "已停用 ") + key if cur.rowcount else "未找到该 Key")


def do_plan(a):
    if a.plan not in PLANS:
        print("套餐只能是", PLANS); sys.exit(2)
    c = ensure(); cur = c.execute("UPDATE api_keys SET plan=? WHERE key=?", (a.plan, a.key))
    c.commit(); c.close()
    print(("套餐已改为 %s " % a.plan) + a.key if cur.rowcount else "未找到该 Key")


def main():
    p = argparse.ArgumentParser(description="开放API Key 管理")
    sub = p.add_subparsers(dest="cmd", required=True)
    pc = sub.add_parser("create"); pc.add_argument("--tenant", default=""); pc.add_argument("--plan", default="trial"); pc.set_defaults(fn=do_create)
    pl = sub.add_parser("list"); pl.set_defaults(fn=do_list)
    pd = sub.add_parser("disable"); pd.add_argument("key"); pd.set_defaults(fn=lambda a: _set_enabled(a.key, 0))
    pe = sub.add_parser("enable"); pe.add_argument("key"); pe.set_defaults(fn=lambda a: _set_enabled(a.key, 1))
    pp = sub.add_parser("plan"); pp.add_argument("key"); pp.add_argument("plan"); pp.set_defaults(fn=do_plan)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
