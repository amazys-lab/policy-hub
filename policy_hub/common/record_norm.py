# -*- coding: utf-8 -*-
"""记录字段注入（city / domain）—— policy_hub 的唯一实现。
------------------------------------------------------------------
背景：同一个"读源库"动作曾有两套实现，行为不同，直接造成 DB 与源库脱节：
  · server/publish_db.py  发版用 —— 不注入 city/domain  → 记录在城市维度上是 None
  · pipeline/loader.py    审计用 —— 注入 city/domain

把注入规则收敛到这里，两处共用。任何"读源库"的新实现都必须调用本模块。

规则（与历史行为一致，勿随意改）：
  city  ：记录自带优先（overseas 域跨城混放在同一文件里），否则取目录名；统一大写
  domain：一律以目录为准（目录不会错；曾出现记录把 domain 写成城市码）

只写标准字段，**不写 `_` 前缀内部字段** —— DB payload 必须保持干净
（实测 816 条 payload 无任何 `_` 字段，这是确权时的可验证性前提）。
"""


def inject(it, city, dom, warn=None):
    """返回注入了 city/domain 的新 dict（不改原对象）。

    warn: 可选回调 warn(item_id, record_domain, dir_domain)，用于上报不一致。
    """
    out = dict(it)
    out["city"] = str(it.get("city") or city).upper()
    raw = it.get("domain")
    if raw and str(raw) != dom and warn is not None:
        warn(it.get("id"), raw, dom)
    out["domain"] = dom
    return out


def check_required(recs):
    """发版前自检：每条记录都必须有 city 与 domain，否则线上列表无法归属城市。
    返回问题清单（空 = 通过）。"""
    bad = []
    for r in recs:
        if not r.get("city"):
            bad.append((r.get("id"), "缺 city"))
        if not r.get("domain"):
            bad.append((r.get("id"), "缺 domain"))
    return bad
