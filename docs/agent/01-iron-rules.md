# 01 · 铁律全文（数据契约与写路径）

## 数据契约八条

1. **枚举 = 机器可判，长句 = 人读**；一字段只装一件事，长句拆 `*_detail`。
2. **加字段必同时加闸门校验**；禁止静默降级（留空或 `to_collect`，绝不用印象补齐）。
3. **可选字段闸门只能「有值才校验」**：空/缺/null/空数组放行（否则存量全红 ⇒ 被 `--skip` 绕过）。
4. **库内键集 ⊆ `schema.*_fields`**：声明漏写 ⇒ 实现顺手漏读（守 `test_contract_key_sync.py`）。
5. **先写断言后改数据**；一个数字写错 ⇒ 同行全重测。
6. **补字段前先统计该字段在目标域的分布**：分布为 0 ⇒ 不许首创（如 `hukou` 域的户籍字段只用 `channel_detail`，从不用 `where`）。
7. **采集准入双条件**：「有官方原文」**且**「采进来能被机器判对适用主体」。缺后者 ⇒ 不采 + 写清结构原因，不许「先塞进去以后补字段」。
8. **「20万」类口径陷阱**：合计金额须在 `amount.text` 写清市/区分担两个数，不许只写合计。

## staging → promote 写路径

```bash
# 改既有记录（推荐先 --dry-run 核对暂存 count / 逐条 id）
python policy_hub/collector/stage.py --patch <城>/<域>/programs.json <patch.json> --dry-run
python policy_hub/collector/stage.py --patch <城>/<域>/programs.json <patch.json>
python policy_hub/collector/promote.py --apply            # 正常晋升（原子 + 回滚点）
python policy_hub/collector/promote.py --apply --force    # 仅当新 URL 不在链接基线时；理由写进提交信息
```

关键语义：

- **`--patch` 不递归**：改子对象须整对象替换；`expect` 用 `r.get(k)!=v` ⇒ 缺键 ≡ `None`，设空值用 `""`。
- **同一 source 的多条记录必须合并成「一条条目 + edits 数组」**：拆多条后者覆盖前者、静默丢改动。
- **新建整城**走不通 `--patch`（源文件须已存在）⇒ 直写 `policy_hub/staging/<城码>/<域>/` → `promote.py`（`target_state()` 有「不存在⇒骨架新建」分支）。
- **不支持删记录**：下线 = `valid` 五值（`active/exited/renamed/merged/superseded`）+ `exit_note`。
- **`--no-clean` 用完必收尾**：再跑一次幂等 `promote --apply`，否则暂存残留、下批重复晋升。
- **回滚**：`promote.py --rollback <时间戳>`（回滚点同时存 `_archive/domains_backup/<ts>`）。

## 迁域（表达「迁出」）

`merge_one()` 按 ID upsert（只增不删），普通 patch **表达不了迁域** ⇒ 用
`policy_hub/staging/_moves/<城码>.json` 声明迁出/迁入，promote 专门消费。

## 变更纪律

- 改完即提交（git）；commit message 写清批次号与 `--force` 理由。
- 派生物（`sources.json` / 链接基线 / 成品）不进闸门 = 必腐：**派生物一律纳入闸门整字典比对**。
- 「报告有日期」≠「跑过」：操作记录须含真实执行证据（计数行、skipped 明确标注）。
- 同一能力两份实现 ⇒ 跑得少的先腐：**判据下沉到唯一函数**（如官方域名判定只在 `link_guard.is_official_host`）。
