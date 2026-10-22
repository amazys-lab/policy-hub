# 02 · 新城采集 SOP

> 每个新城 = 1 个批次（docs/reports/NN- 递增）。目标：8 域全齐（DC1 断言硬约束，缺域必补，禁加白名单）。

## 流程

### ① 注册（5 个登记点 + 2 个易漏点）

跑 `pipeline/register_city_codes.py` 登记城市码，**5 个注册点**全部落地后
重生成 `field_contract.json` 与 `extract_frontend.js`。
易漏的两处：**`CITY_DOMAINS`**（`post_collect_check.py` + `healthcheck.py`，该城官方域名）
与 **`cond` 字段池**（`city_kind[城]`，从前端控件池生成）。

### ② 封锁探测

- 裸 `curl -sL -A <UA>` 试门户与深栏各一页。
- 403/412/521 ⇒ 逐个试：`Referer: https://<host>/`（多站救命）、镜像前缀、省级站点直达。
- **单次失败永不作死链结论**；判死只有 404/410。
- 经验先查 `06-fetching.md`，同款 WAF 可能有现成解法。

### ③ 8 域采集

每域 ≥3 条，每条必须：官方原文 URL + 文号 + 发布日期 + 机器可判条件。
- 域载体：`hukou` = `channels.json`（键 `channels`，`result_type:"channel"`）；其余域 = `programs.json`。
- overseas 域不看 `applicant_kinds`，一律走 `kind_global.overseas`（`os_*` 前缀字段池）。
- 写不进机器条件的（前端无控件/池里没有）⇒ 落 `cond.manual_check`，**不造幽灵条件**。
- `apply_url` 无稳定线上入口就**如实留空**（空合法），路径写 `channel_detail`。
- `source_doc` 客户可见窗口 **300 字**：写短版文档串（文号+印发日+有效期），超长必被截断成错。

### ④ 正序入库（顺序不可乱）

```bash
# 1. staging 直写或 --patch（先 --dry-run 核对）
python policy_hub/collector/promote.py --apply --force --no-clean   # 新 URL 不在基线，强制；理由入 commit
# 2. 链接基线收录新 URL
python policy_hub/collector/link_verify.py --scope all --emit-audit
# 3. 源清单
python policy_hub/collector/build_sources.py
# 4. 闸门真实裁决
python policy_hub/collector/gate_validate.py        # 期望 0 红
# 5. 内容一致性
python policy_hub/collector/link_match.py
# 6. 全量 pytest（--basetemp 仓内！）
```

### ⑤ 收尾

- 幂等 `promote --apply` 清暂存（若用过 `--no-clean`）。
- 分类器「未归类」的 guide_url：人工开正文核对后进 `known_issues.guide_url_review` 台账
  （`{key:"ID|url", id, class:"未归类", verdict:"原文", why:"...事实描述"}`）。
- 重出受影响成品（改了基线/枚举/geo/`CITY_DOMAINS` 后**必重出**）。
- DB 发布（先备份，见 `08-release.md`）→ 报告 `docs/reports/NN-` → git 提交 → 技能/记忆更新。

## 验收标准

- 闸门 0 红；DC1 断言绿（8 域齐，`KNOWN_GAPS` 保持 `{}`）
- pytest 计数行不低于基线（新增红 = 未收尾）
- `link_match` 0 MISMATCH / 0 DEAD
- 成品重出且 `verify_output` V1–V9 全绿
