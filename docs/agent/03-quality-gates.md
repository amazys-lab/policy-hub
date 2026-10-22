# 03 · 三闸门、台账与 pytest

## 质检三层

| 层 | 工具 | 拦什么 |
|---|---|---|
| 链接层 | `link_verify.py --scope all --emit-audit` | 死链/不可达/文种分类；产出链接基线 + `link_audit.json` |
| 源清单层 | `build_sources.py` | 每条记录必须有官方源；产出 `sources.json`（派生物，纳入闸门整字典比对） |
| 闸门层 | `gate_validate.py` | 30+ 项契约校验（字段白名单、枚举、字段位置、链接角色、新鲜度…），期望 `N / 0` |

内容一致性另跑 `link_match.py`（客户可见 URL ↔ 原文匹配，期望 0 MISMATCH / 0 DEAD）。

## 关键判据（错过的代价都付过）

- **判死只有 404/410**。000/超时/403/412/502 都是「故障」不是「死链」——先复测（定点长超时、带 Referer），再下结论；复测脚本回写，不手填结论。
- **三闸门只扫 `guide_url` / `apply_url` / `sources`** ⇒ `channel_detail` 里的域名是盲区，采集时自查。
- **`guide_slot_ok()` 严于 `degrade()`**：首页/栏目/新闻/非原文进不了 `guide_url`。
- **「判原文页」≠「是原文」**：分类器通过后仍须人工开正文核对（尤其文号、金额、期限）。
- **`apply_url` 只认线上可操作入口**；`被拦截(403/412)` 可作 `apply_url` 不可作 `guide_url`；空合法。

## 台账机制（`policy_hub/common/known_issues.json`）

- `guide_url_review`：分类器判「未归类」的正规放行通道。**放行须人工判定**：
  ```json
  {"key":"XX-OS-001|https://...","id":"XX-OS-001","class":"未归类",
   "verdict":"原文","why":"人工开正文核对到文号演示规〔2025〕1号…"}
  ```
- **verdict 限 `原文` 或 `清单/摘要`**（后者须举证：省级基准或只有问答页形态）。
- 台账条数**必现算**，不许在文档里硬编码。
- 台账不是垃圾场：每条 why 必须是可复核的事实描述。

## pytest 约定

```bash
python -m pytest -p no:cacheprovider -o addopts="" -q --basetemp=_tmp/pytest
```

- **`--basetemp` 必须指向仓内目录**：Windows 默认 temp 收尾删除会撞 `safe-delete` 钩子 ⇒ `rc=1` 假失败。
- **判据是尾部计数行**（`N passed, M skipped, K failed`），不是 `rc`。
- **复用/并发 basetemp 会造出假 `ERROR at setup`**：换干净目录重跑即消失；先单文件单跑定位。
- 红测试的处理顺序：读报错 → 复现 → 修数据/修代码 → **禁止改断言凑绿**。
- 「成品待重出」造成的红是预期红（成品晚于源库），须尽快重出清零，长期挂着会淹没真红。
