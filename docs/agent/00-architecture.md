# 00 · 架构与真值源

## 目录布局

```
policy_hub/
  common/        # field_contract.json（字段契约）、enum_map、geo、known_issues（台账）
  collector/     # 采集与质检全部脚本（stage / promote / gate_validate / link_verify ...）
  domains/       # ★ 权威数据（唯一真值源，只读——改动走 staging）
    cities/<城码>/<域>/programs.json | channels.json
    <域>/*.json                # 顶层载体（历史布局，loader 兼容两种）
pipeline/        # loader / export_excel / release_matrix / mappers ...
server/          # FastAPI（app.py）、publish_db.py、static/ 前端
_scripts_history/<批次>/   # 一次性脚本归档（gitignore）
output/          # 成品（gitignore）
```

## 数据流（单向）

```
官方原文 URL
  → staging（policy_hub/staging/<城>/<域>/，可 --dry-run 预览）
  → promote.py --apply（原子落 domains/**，自动回滚点 _archive/domains_backup/<ts>）
  → 派生物刷新：link_verify（链接基线）→ build_sources（源清单）→ gate_validate（闸门）
  → 成品：export_excel（release_matrix.py 是成品配方真值源）
  → 发布：server/publish_db.py（DB 版本化）→ uvicorn
```

## 真值源归属（一处一真值，别处只读）

| 问题 | 真值源 |
|---|---|
| 政策记录 | `policy_hub/domains/**`（经 `pipeline/loader.load_all()` 读取） |
| 字段合法性 | `policy_hub/common/field_contract.json`（含 `city_kind[城]` 控件池） |
| 域中文文案 | `enum_map.json` 三表 |
| 城市官方域名 | `post_collect_check.CITY_DOMAINS`（登记点共 5 处） |
| 成品配方 | `pipeline/release_matrix.py`（条数现算，行键=id） |
| 官方链接判定 | `pipeline/link_guard.is_official_host` |
| C 端收录口径 | `pipeline/audience.py` |
| 台账/例外 | `policy_hub/common/known_issues.json` |

## 加载数据的唯一姿势

```python
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'pipeline')
from loader import load_all
rows = load_all('<仓根>')   # 兼容两种目录布局与五种载体键（programs/channels/windows/catalog/points_cutoff）
```

★ **永远不要自写 glob 扫 domains/**——布局有两种、载体键有五种，自写扫描必错
（历史上 AI 两次统计翻车都源于此）。统计一律走 `load_all()` 或 `release_matrix.py`。
