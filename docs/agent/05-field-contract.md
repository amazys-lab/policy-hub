# 05 · 字段契约要点

真值源：`policy_hub/common/field_contract.json`（改完必重生成 + 跑 `test_contract_key_sync.py`）。

## 控件池（`city_kind[城]`）

每城有四池：`person`（个人）/ `entrepreneur`（创业者）/ `unit`（单位）/ `hukou`（户籍）。
**条件字段只能来自对应池**；池里没有的字段写进 `cond` ⇒ 闸门报「幽灵条件」⇒ 落 `cond.manual_check`。

- **overseas 域特殊**：不看 `applicant_kinds`，一律走 `kind_global.overseas`（`os_*` 前缀字段，19 个）。unit 字段进 overseas 的 cond 必报幽灵。
- `contract_years` 在 person/entrepreneur/unit 池，**不在** hukou / overseas 池。
- 常见池内字段：`ent_scale / ui_paid_months / ui_premium_lastyear / no_layoff / layoff_rate_ok / not_zombie / is_sme_tech / rd_expense`（unit）；`personal_ss_months / works_at_smb / no_self_house / no_housing_benefit / no_transfer_3y`（person）。

## 枚举白名单（闸门强校验）

| 字段 | 白名单 |
|---|---|
| `ptype` | 31 值（`gate_validate.PTYPE_WHITELIST`） |
| `channel_type` | 10 值 |
| `window_type` | 仅 `公安派出所户籍窗口` / `人社部门窗口` |
| `valid` | `active / exited / renamed / merged / superseded` |
| `ent_scale` | `smb / large / individual` |
| `applicant_kinds` | 顺序必须规范序（如 `["entrepreneur","overseas"]`） |

- `ptype` 无值**留空**（不许硬凑）；`once` 型金额必有 `value`，多档用 `range`（min 可 None）。
- 枚举「近义归并」不许随手新增值——先查全库分布与 36- 归并表。

## 常见「写不进去」的正确落点

| 想表达 | 为什么写不进 | 落点 |
|---|---|---|
| 持股/份额百分比（`os_share`） | 前端是布尔勾选框 | `{"op":"==","v":true}` |
| 八类近亲属投靠 | 前端下拉仅 `spouse/minor_child/elder_parent` | `manual_check` |
| 区级/园区奖励的主体判定 | 池里无 `in_park/has_district` | **不采**（准入双条件） |
| 合同年限（hukou/overseas） | 池里没有 | `manual_check` |

## 字段位置契约

- 执行状态三字段在 `deadline.*`（`exec_status / expire / expire_text`），写顶层会被闸门 27 拦。
- `amount.text` 涉及「市+区合计」必须写两个数。
- `source_doc` ≤ 300 字（`mappers.SOURCE_DOC_MAX`），括号必须配对，同一文号只引述一次。
- `sources` 域文件里是**字符串数组**（部分历史城），统一读取前先判型。
