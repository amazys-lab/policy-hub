# -*- coding: utf-8 -*-
"""
开放 API（/open/v1）：API Key 鉴权 + 套餐限流 + 用量计数骨架（阶段B）
------------------------------------------------------------------
- 产品前端自用的 /api/v1 保持不变（同源、无需 Key）；
- 对外第三方/多租户走 /open/v1，必须带请求头 X-API-Key；
- Key 用 `python -m server.api_keys` 命令行签发/停用/改套餐，存在 policy.db；
- 限流：内存滑动窗口(每分钟) + SQLite 当日计数(每天)，超限返回 429；
- 每次调用写 usage_logs，可自查用量。阶段B为本地骨架，不接真实支付/网关。
"""
import os, sqlite3, time, datetime, collections
from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, Depends, HTTPException
from pydantic import BaseModel

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.db")
router = APIRouter(prefix="/open/v1", tags=["开放API(需 X-API-Key)"])

# 套餐配额（阶段B骨架，数值可按运营调整；正式计费在支付/网关层叠加）
PLAN_LIMITS = {
    "trial": {"per_min": 10,  "per_day": 50},
    "free":  {"per_min": 20,  "per_day": 200},
    "pro":   {"per_min": 300, "per_day": 50000},
}
_win = collections.defaultdict(collections.deque)  # key -> 近60秒请求时间戳


def _conn():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c


def ensure_tables():
    c = _conn()
    c.execute("CREATE TABLE IF NOT EXISTS api_keys("
              "key TEXT PRIMARY KEY, tenant TEXT, plan TEXT DEFAULT 'trial',"
              "enabled INTEGER DEFAULT 1, created_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS usage_logs("
              "id INTEGER PRIMARY KEY AUTOINCREMENT, key TEXT, ts TEXT,"
              "endpoint TEXT, status INTEGER)")
    c.commit(); c.close()


def _log(key, endpoint, status):
    try:
        c = _conn()
        c.execute("INSERT INTO usage_logs(key,ts,endpoint,status) VALUES(?,?,?,?)",
                  (key, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), endpoint, status))
        c.commit(); c.close()
    except Exception:
        pass


def gate(key: Optional[str], endpoint: str):
    ensure_tables()
    if not key:
        raise HTTPException(401, "缺少 X-API-Key 请求头；用 python -m server.api_keys create 签发")
    c = _conn(); row = c.execute("SELECT * FROM api_keys WHERE key=?", (key,)).fetchone(); c.close()
    if not row:
        raise HTTPException(401, "API Key 无效")
    if not row["enabled"]:
        _log(key, endpoint, 403); raise HTTPException(403, "该 API Key 已停用")
    plan = row["plan"] or "trial"; lim = PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])
    now = time.time(); dq = _win[key]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= lim["per_min"]:
        _log(key, endpoint, 429)
        raise HTTPException(429, "超过每分钟上限 %d 次，请降速或升级套餐" % lim["per_min"])
    today = datetime.date.today().isoformat()
    c = _conn()
    day_n = c.execute("SELECT COUNT(*) FROM usage_logs WHERE key=? AND ts LIKE ? AND status=200",
                      (key, today + "%")).fetchone()[0]; c.close()
    if day_n >= lim["per_day"]:
        _log(key, endpoint, 429)
        raise HTTPException(429, "超过今日上限 %d 次，次日重置或升级套餐" % lim["per_day"])
    dq.append(now)
    return row


def auth(x_api_key: Optional[str] = Header(default=None)):
    return gate(x_api_key, "")


class OpenIn(BaseModel):
    profile: Dict[str, Any] = {}
    brand: Optional[Dict[str, Any]] = None


# 端点（依赖里做鉴权与限流，成功后记 200）
@router.get("/meta", include_in_schema=True)
def open_meta(x_api_key: Optional[str] = Header(default=None)):
    from server.app import build_meta
    row = gate(x_api_key, "meta"); out = build_meta()
    out["tenant"] = row["tenant"]; out["plan"] = row["plan"]
    _log(row["key"], "meta", 200); return out


@router.get("/policies")
def open_policies(domain: Optional[str] = None, city: Optional[str] = None,
                  q: Optional[str] = None, limit: int = 200,
                  x_api_key: Optional[str] = Header(default=None)):
    """政策清单（供 MCP / agent 做「先找再取详情」的第一步）。

    ★ 2026-10-21 新增：开放 API 原先把 `policies` 列表端口开了 —— 只有 match / policy/{id}，
      调用方拿不到 id 就无从 match，等于**入口在屋里**。MCP 的 `search_policies` 依赖它。
    `limit` 只截返回条数，不动 `count`（count 永远是筛选结果的全量，避免调用方误判总量）。
    """
    from server.app import list_policies
    row = gate(x_api_key, "policies")
    out = list_policies(domain=domain, city=city, q=q)
    items = out.get("items") or []
    if limit and len(items) > limit:
        out = dict(out)
        out["items"] = items[:limit]
        out["truncated"] = True
    out["tenant"] = row["tenant"]; out["plan"] = row["plan"]
    _log(row["key"], "policies", 200); return out


@router.post("/match")
def open_match(body: OpenIn, x_api_key: Optional[str] = Header(default=None)):
    from server.app import run_match
    row = gate(x_api_key, "match"); out = run_match(body.profile or {})
    out["tenant"] = row["tenant"]; out["plan"] = row["plan"]
    _log(row["key"], "match", 200); return out


@router.post("/checklist")
def open_checklist(body: OpenIn, x_api_key: Optional[str] = Header(default=None)):
    from server.app import run_checklist
    row = gate(x_api_key, "checklist"); out = run_checklist(body.profile or {}, body.brand)
    out["tenant"] = row["tenant"]
    _log(row["key"], "checklist", 200); return out


@router.get("/policy/{item_id}")
def open_policy(item_id: str, x_api_key: Optional[str] = Header(default=None)):
    from server.app import POL, DATA_VERSION
    row = gate(x_api_key, "policy"); p = POL.get(item_id)
    if not p:
        _log(row["key"], "policy", 404)
        raise HTTPException(404, "未找到政策条目: %s（当前版本 %s）" % (item_id, DATA_VERSION))
    _log(row["key"], "policy", 200)
    return {"data_version": DATA_VERSION, "policy": p, "tenant": row["tenant"]}


@router.get("/usage")
def open_usage(x_api_key: Optional[str] = Header(default=None)):
    row = gate(x_api_key, "usage"); key = row["key"]
    today = datetime.date.today().isoformat()
    week = (datetime.date.today() - datetime.timedelta(days=6)).isoformat()
    c = _conn()
    today_n = c.execute("SELECT COUNT(*) FROM usage_logs WHERE key=? AND ts LIKE ? AND status=200",
                        (key, today + "%")).fetchone()[0]
    week_rows = c.execute("SELECT endpoint,COUNT(*) n FROM usage_logs WHERE key=? AND ts>=? AND status=200 GROUP BY endpoint",
                          (key, week)).fetchall()
    c.close()
    plan = row["plan"] or "trial"; lim = PLAN_LIMITS.get(plan, PLAN_LIMITS["trial"])
    return {"tenant": row["tenant"], "plan": plan,
            "limits": lim, "used_today": today_n, "remain_today": max(0, lim["per_day"] - today_n),
            "last7d_by_endpoint": {r["endpoint"]: r["n"] for r in week_rows}}
