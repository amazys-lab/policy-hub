# -*- coding: utf-8 -*-
"""Policy Hub · MCP Server

把政策库包成 AI agent 可直接调用的工具（Claude Code / Cursor / WorkBuddy / Codex 等）。

两种后端
--------
1. **本地模式（默认）**：与本仓同目录运行，直接 import 引擎，零配置、无鉴权。
2. **远程模式**：设 `POLICY_HUB_URL`（可选 `POLICY_HUB_KEY`），走开放 API `/open/v1/*`。
   适合「服务端部署一次，多台机器上的 agent 连过来」。

启动（stdio，由 MCP 客户端拉起）
------------------------------
    python -m mcp_server.server

客户端配置示例（Claude Code / Cursor 的 mcpServers）
----------------------------------------------------
    {
      "mcpServers": {
        "policy-hub": {
          "command": "python",
          "args": ["-m", "mcp_server.server"],
          "cwd": "<本仓路径>"
        }
      }
    }

设计取舍
--------
- **为什么不让 AI 读原文自己判断**：资金、期限、资格必须精确。「最高 3 万」与「最高 10 万」
  在语义检索里只差几个 token，在窗口审核那里差一整笔钱。这里走结构化字段 + 规则引擎。
- **工具返回值刻意精简**：`search_policies` 只回摘要（不含全文），`get_policy` 才给全字段，
  且长文本截断 —— MCP 的返回值直接进对话上下文，返回 376KB 的 HTML 会直接把上下文打爆。
- **不在文档里写判定规则**：规则唯一真值源在 `policy_hub/engine`，本文件只做搬运，
  绝不复制第二份判据（一事两判据＝没人管）。
"""
import os
import sys
from typing import Any, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (ROOT, os.path.join(ROOT, "policy_hub")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcp.server.mcpserver import MCPServer

BASE = (os.environ.get("POLICY_HUB_URL") or "").rstrip("/")
KEY = os.environ.get("POLICY_HUB_KEY") or ""

mcp = MCPServer(
    name="policy-hub",
    version="0.1.0",
    instructions=(
        "中文就业创业补贴 / 落户通道 / 人才引进政策的查询与匹配。"
        "典型顺序：search_policies 找政策 → match_profile 判能不能报 → "
        "get_policy 看原文细节 → get_checklist 拿材料清单。"
        "金额与资格均为规则估算，最终以官方文件与窗口核定为准；"
        "不要替用户承诺能拿到钱，也不要编造没查到的政策。"
    ),
)

# search_policies 返回的字段白名单：只回摘要，全文走 get_policy
_SUMMARY_KEYS = ("id", "name", "domain", "city", "result_type", "amount_hint",
                 "window", "valid", "deadline", "source_doc", "updated_at")
# get_policy 里长文本字段的截断长度（防上下文被打爆）
_TEXT_CAP = 2000

_APP = None


def _app():
    """懒加载 server.app（它会读全库，约 1-3 秒，只在首次调用时付这个成本）。"""
    global _APP
    if _APP is None:
        from server import app as _a
        _APP = _a
    return _APP


def _remote(path: str, params: Optional[Dict[str, Any]] = None,
            body: Optional[Dict[str, Any]] = None, method: str = "GET") -> Dict[str, Any]:
    import requests
    headers = {"X-API-Key": KEY} if KEY else {}
    r = requests.request(method, BASE + path, params=params, json=body,
                         headers=headers, timeout=30)
    if r.status_code == 404:
        raise ValueError(r.text[:200])
    r.raise_for_status()
    return r.json()


def _slim(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{k: it[k] for k in _SUMMARY_KEYS if it.get(k) not in (None, "", [])}
            for it in items]


def _name_index(city: str, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """按需给 ID 补名称/金额 —— **一次取该城清单**，不做 N+1 逐条请求。"""
    if not ids:
        return {}
    if BASE:
        rows = (_remote("/open/v1/policies", params={"city": city, "limit": 500}).get("items") or [])
    else:
        rows = (_app().list_policies(city=city).get("items") or [])
    idx = {r["id"]: r for r in rows if r.get("id")}
    keep = ("id", "name", "domain", "amount_hint", "window", "valid")
    return {i: {k: idx[i][k] for k in keep if idx[i].get(k) not in (None, "")}
            for i in ids if i in idx}


@mcp.tool()
def search_policies(city: str = "", keyword: str = "", domain: str = "", limit: int = 20) -> Dict[str, Any]:
    """按城市 / 关键词 / 域检索政策清单。**只返回摘要，不含正文** —— 拿到 id 后再用 get_policy。

    Args:
        city: 城市码，见 policy_hub/common/schema.json 的 city_code（如 SZ / NN / CD）；留空 = 全部城市
        keyword: 政策名称关键词，如「创业补贴」「落户」「培训」
        domain: 域，可选 employment_startup(就业创业) / tech_enterprise(高企) /
                vocational_training(技能培训) / housing(住房) / hukou(落户) /
                inclusive_tax(普惠税费) / enterprise_support(企业扶持) / overseas(留学人才)
        limit: 最多返回条数，默认 20，上限 200

    Returns:
        {total, returned, items:[{id,name,domain,city,amount_hint,window,valid,...}]}
        total 是筛选结果的全量条数，returned 是本次实际返回条数。
    """
    limit = max(1, min(int(limit or 20), 200))
    if BASE:
        j = _remote("/open/v1/policies", params={"city": city, "q": keyword,
                                                 "domain": domain, "limit": limit})
        items, total = j.get("items") or [], j.get("count", 0)
    else:
        j = _app().list_policies(domain=domain or None, city=city or None,
                                 q=keyword or None)
        items, total = (j.get("items") or [])[:limit], j.get("count", 0)
    return {"total": total, "returned": len(items), "items": _slim(items)}


@mcp.tool()
def match_profile(city: str, kind: str = "person",
                  profile: Optional[Dict[str, Any]] = None,
                  limit: int = 10) -> Dict[str, Any]:
    """按画像判断能申报哪些政策（规则引擎判定，不是模型猜的）。

    Args:
        city: 城市码，如 SZ / GZ / FZ
        kind: 主体类型 —— person(个人) / entrepreneur(创业者) / unit(单位) / overseas(留学回国)
        profile: 其余画像字段，键见 list_profile_fields()。常用：
                 age, edu, identities(如 ["graduate"]), contract_years,
                 personal_ss_months, ent_ss_months, ent_scale,
                 biz_reg_months, staff_count, has_training_cert
        limit: 每类最多返回几条，默认 10

    Returns:
        {city, matched:[...], near:[...], hukou:[...], 其余非空分组, disclaimer}
        只返回**有结果的**分组；空分组直接省略，避免一堆空数组占上下文。
    """
    prof = dict(profile or {})
    prof["city"] = (city or "").upper()
    prof["kind"] = kind or "person"
    if BASE:
        r = _remote("/open/v1/match", body={"profile": prof}, method="POST")
    else:
        r = _app().run_match(prof)

    summary = r.get("summary") or {}
    # summary 里各组要么是 ID 列表、要么是计数 / 状态字符串
    lists = {k: v for k, v in summary.items() if isinstance(v, list) and v}
    all_ids = sorted({i for v in lists.values() for i in v if isinstance(i, str)})
    idx = _name_index(prof["city"], all_ids)

    out: Dict[str, Any] = {"city": prof["city"], "kind": prof["kind"]}
    for k, ids in lists.items():
        rows = [idx[i] for i in ids[:limit] if i in idx]
        out[k] = rows or ids[:limit]
    out["counts"] = {k: (len(v) if isinstance(v, list) else v) for k, v in summary.items()}
    out["data_version"] = r.get("data_version", "")
    out["disclaimer"] = r.get("disclaimer", "")
    return out


@mcp.tool()
def get_policy(policy_id: str) -> Dict[str, Any]:
    """取单条政策的完整字段（金额规则、申报条件、材料、办理入口、原文链接）。

    Args:
        policy_id: 政策 ID，如 XX-EMP-001（由 search_policies 或 match_profile 得到）

    Returns:
        {data_version, policy:{...}}；超长文本字段已截断到 2000 字并标注 truncated。
    """
    if BASE:
        j = _remote("/open/v1/policy/" + policy_id)
    else:
        try:
            j = _app().policy(policy_id)
        except Exception as e:  # HTTPException(404)
            raise ValueError("未找到政策条目 %s：%s" % (policy_id, e))
    p = dict(j.get("policy") or {})
    truncated = []
    for k, v in list(p.items()):
        if isinstance(v, str) and len(v) > _TEXT_CAP:
            p[k] = v[:_TEXT_CAP]
            truncated.append(k)
    return {"data_version": j.get("data_version", ""), "policy": p,
            "truncated_fields": truncated}


@mcp.tool()
def get_checklist(city: str, kind: str = "person",
                  profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """生成可直接给客户看的「可申报清单 + 材料 + 办理入口」纯文本。

    Args:
        city: 城市码
        kind: 主体类型 person / entrepreneur / unit / overseas
        profile: 其余画像字段，同 match_profile

    Returns:
        {title, text, summary, disclaimer}；text 是排版好的多行文本，可直接展示。
    """
    prof = dict(profile or {})
    prof["city"] = (city or "").upper()
    prof["kind"] = kind or "person"
    if BASE:
        r = _remote("/open/v1/checklist", body={"profile": prof}, method="POST")
    else:
        r = _app().run_checklist(prof, None)
    return {"title": r.get("title", ""), "text": r.get("text", ""),
            "data_version": r.get("data_version", ""),
            "disclaimer": r.get("disclaimer", "")}


@mcp.tool()
def list_profile_fields() -> Dict[str, Any]:
    """列出画像可用的全部字段及出现频次，供构造 match_profile 的 profile 参数。

    返回值按频次降序 —— 频次越高说明越多政策依赖它，填了收益越大。
    """
    if not BASE:
        try:
            import collections
            from pipeline import loader
            rows = loader.load_all(ROOT)
            freq = collections.Counter()
            kinds = collections.Counter()
            for r in rows:
                cond = r.get("cond") or {}
                for m in (cond.get("must") or []):
                    if isinstance(m, dict) and m.get("f"):
                        freq[m["f"]] += 1
                for k in (cond.get("applicant_kinds") or []):
                    kinds[k] += 1
            return {"fields": dict(freq.most_common()),
                    "kinds": dict(kinds),
                    "note": "fields 为 cond.must 里出现过的画像字段及频次；kinds 为主体类型分布"}
        except Exception as e:
            return {"error": "本地读取失败：%s" % e}
    # 远程模式没有对应端点，给一份常用字段表兜底
    return {"fields": {k: None for k in (
                "contract_years", "ent_ss_months", "identities", "ent_types",
                "normal_operation", "is_legal_rep", "os_degree", "os_district",
                "os_age", "ui_paid_months", "biz_reg_months", "personal_ss_months",
                "ent_scale", "has_training_cert", "no_credit_violation",
                "hire_grad2y_count", "hire_keygroup_count", "staff_count", "age", "edu")},
            "kinds": ["person", "entrepreneur", "unit", "overseas"],
            "note": "远程模式下列表为常用字段，频次需连本地或调 /api/v1/meta 获取"}


if __name__ == "__main__":
    mcp.run()
