# AGENTS.md — AI 操作员入口

> 本项目由 AI agent 长期维护（数据采集 → 质检 → 成品交付全链路）。
> 本文件是任何 AI（Codex / Claude Code / Cursor / WorkBuddy 等）接手操作的入口。
> 目标：**接上即能干活，干了也坏不了**。

## 项目是什么

政策数据管线：从全国政府官网采集人才补贴 / 创业补贴 / 技能培训补贴等 8 个域的政策，
结构化入库,经三重闸门质检后产出 B 端 Excel、C 端 Excel、前端看板与开放 API。

- ★ 本开源仓是 open core：**`policy_hub/domains/` 不附带任何数据，克隆下来是空库**。
  引擎、字段契约、校验、导出、MCP 全在；政策条目由使用者自行采集填入
  （见 `policy_hub/domains/README.md`）。条数一律现算（`python pipeline/check_data.py`），
  勿信文档里的任何历史数字。

> ⚠️ **本仓是精简版**：下面手册里提到的 `stage.py` / `promote.py` / `gate_validate.py` /
> `link_verify.py` / `build_sources.py` 等采集质检脚本**未随仓分发**。仓内可直接跑的是：
> `pipeline/check_data.py`（数据自检）、`pipeline/` 其余导出与校验脚本、`server/`（服务）、
> `mcp_server/`（MCP）、`policy_hub/engine/`（匹配引擎）。
- 域（8 个固定）：`employment_startup / tech_enterprise / vocational_training / housing / hukou / inclusive_tax / enterprise_support / overseas`

## 5 分钟跑通

```bash
pip install -r requirements.txt
python run.py          # 探测 python → 生成 DB（server/policy.db）→ 起 FastAPI
# 或手工：
python -m server.publish_db "备注"   # 生成/刷新 DB
uvicorn server.app:app --port 8700
```

跑测试（**必须带仓内 `--basetemp`**，否则 Windows 下默认 temp 清理会撞删除钩子产生假失败）：

```bash
python -m pytest -p no:cacheprovider -o addopts="" -q --basetemp=_tmp/pytest
```

判据是输出**尾部计数行**，不是退出码 `rc`。

## 三条铁律（违反 = 数据作废）

1. **不编数据**：每条记录必须有官方原文（URL + 文号），且适用主体能被机器判对。
   采不进来就写清结构原因，**绝不**用印象补齐、绝不静默降级。
2. **唯一写路径**：改数据只走 `policy_hub/collector/stage.py --patch [--dry-run]` → `promote.py --apply`。
   直接改 `policy_hub/domains/**` = 破坏回滚与审计。
3. **改完必复验**：任何数据/判据改动后依次跑
   `build_sources` → `gate_validate` → `link_verify`（改了 URL 时）→ `pytest`，
   然后重出受影响的成品（改数据不重出成品 = 客户看到旧数字）。

## 收尾仪式（每次操作结束跑一遍）

```bash
python policy_hub/collector/build_sources.py
python policy_hub/collector/gate_validate.py        # 期望：0 红
python -m pytest -q --basetemp=_tmp/pytest          # 期望：计数行与基线一致
```

闸门红 = 停下来修，**不是**绕过。

## 深入阅读（docs/agent/）

| 文件 | 内容 |
|---|---|
| `00-architecture.md` | 目录布局、数据流、真值源归属 |
| `01-iron-rules.md` | 数据契约与写路径的完整规则 |
| `02-collect-new-city.md` | 新城采集 SOP（注册点 → 封锁探测 → 8 域 → 正序入库） |
| `03-quality-gates.md` | 三闸门、台账机制、pytest 约定 |
| `04-pitfalls.md` | 踩坑录精编（历史上真实炸过的坑，按主题归档） |
| `05-field-contract.md` | 字段契约要点：控件池、枚举白名单、幽魈条件 |
| `06-fetching.md` | 抓取经验：WAF/Referer/编码/附件/正文抽取 |
| `07-links.md` | 链接基线、文种分类器、guide_url_review 台账 |
| `08-release.md` | 成品出库、DB 发布、回滚、发布矩阵 |

## 红线速查

- 禁止直接编辑 `policy_hub/domains/**`（走 staging）
- 禁止跳过闸门（`--force` 仅用于「新 URL 尚未入基线」这一种合法场景，理由写进提交信息）
- 禁止改测试让红变绿（如 `source_doc` 300 字上限——改数据，不改阈值）
- 禁止编造条数/数字——一切计数现算（`loader.load_all()` / `release_matrix.py`）
- 禁止把一次性脚本留在仓根——放 `_scripts_history/<批次>/`
