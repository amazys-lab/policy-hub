# 08 · 成品出库、DB 发布与回滚

## 成品配方

真值源 = `pipeline/release_matrix.py`（`recalc_rows(job)` 现算，行键=`id`）。
**条数绝不硬编码**；成品缺失 = fail 不是 skip。

出成品（逐条显式传 `--title`，勿 shell 循环；改完 `ls` 核对）：

```bash
python pipeline/export_excel.py --job <preset> --title "<标题>" ...
python pipeline/verify_output.py <成品.xlsx>   # V1–V9 全绿才算过（只吃 Excel，main() 收字符串返退出码）
```

要点：

- `loader.load_all(src)` 的 `src` = **仓根**；`filter_cities(rows, 码列表)` 不吃 preset 名。
- B 端 Excel 三 Sheet 起；C 端 = 多城 Excel + 单城 Excel（20 列、城市列第 4、冻结 E2）。
  成品形态统一 Excel：链接可点、列宽可筛、可直接转发，客户拿到手就能用。
- C 端只收个人可申报（真值源 `pipeline/audience.py`）；七字段缺项跳整行。

**隔离性铁律**：加新城只许 `all` / `c_all` 变；存量城补域则各 preset 同步变。
引用条数写 **active / 成品** 两个口径。

## DB 发布

```bash
# 发布前后各手工备份一份（脚本无自动备份！）
cp server/policy.db "_archive/db_backup/policy_before_<批次>_$TS.db"
python -m server.publish_db "<版本备注>"
cp server/policy.db "_archive/db_backup/policy.db.$TS.post.bak"
# 核验：版本内总条数 / 分域计数 / 新城条数 与 domains 现算一致
```

## 回滚

| 对象 | 方法 |
|---|---|
| domains 数据 | `python policy_hub/collector/promote.py --rollback <时间戳>`（回滚点同时在 `_archive/domains_backup/<ts>`） |
| DB | 用 `_archive/db_backup/` 对应备份覆盖；版本号顺延新发布 |
| 成品 | `output/` 归档在 `_archive/`，重出即可 |

## 发版检查单

1. 闸门 0 红（`gate_validate`）
2. `link_match` 0 MISMATCH / 0 DEAD
3. pytest 计数行不低于基线
4. 受影响成品已重出且 `verify_output` V1–V9 绿
5. DB 发布前后备份齐全，条数核验一致
6. 报告 `docs/reports/NN-` 已写，git 已提交
