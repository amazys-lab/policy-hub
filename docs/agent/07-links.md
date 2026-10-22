# 07 · 链接基线、分类器与台账

## 链接角色（三端统一）

| 字段 | 角色 | 判据 |
|---|---|---|
| `guide_url` | 申报指南/政策原文页 | 须过 `guide_slot_ok()`（严于降级判据）：首页/栏目/新闻/非原文进不来 |
| `apply_url` | 线上办理入口 | 只认可操作入口；空合法；被拦截(403/412)的页面可作 apply 不可作 guide |
| `sources[]` | 官方依据源 | 每条记录 ≥1；进 `sources.json` 派生物并纳入闸门整字典比对 |
| `entry_url` | 成品渲染的办理入口 | 取自 `apply_url`，无回退 |

选链真值源 = `original_doc_url()`（`pipeline/link_guard.py`），三端统一调用，**不许**各写一份。

## 基线操作

```bash
python policy_hub/collector/link_verify.py --scope all --emit-audit   # 重建基线 + link_audit.json
```

- 新 URL 入基线正序：staging 修完 → `promote --apply --force`（闸门项②「不在基线」拦新 URL）→ `link_verify` → `build_sources` → 复跑 `gate_validate`。
- `--force` 的理由必须写进提交信息。
- 「不可达」须用同一分类器定点长超时复测回写（脚本化，不手填结论）。

## 分类器纪律

- 四态口径：①不在基线=拦 ②不合格=拦 ③**未归类=进台账等人工判定** ④合格=放行。
  `cls_of(...) or "未归类"` 这种写法会吃掉三态，禁止。
- 改判据放 `classify()` **末步**（位置 > 阈值）；改完交「其余类计数不变」验证。
- 空壳页（正文<N 但确实是原文页）**不放出闸门**：仍进 `GUIDE_OK_KINDS`，把关挪到举证
  （`guide_url_shell` 三态），因为「抓不到 ≠ 客户看不到」。

## 台账（guide_url_review）

- 用途：未归类的正规放行通道；**verdict 限 `原文` 或 `清单/摘要`**。
- key 格式 `"<ID>|<url>"`；每条 why 是可复核的事实（文号、条款、开正文核对到的要点）。
- 台账条数现算；「撤回错误推理」优先于「加判据放行」。

## 内容一致性

`link_match.py`：客户可见 URL ↔ 原文内容匹配，产出 MATCH / MISMATCH / UNKNOWN / DEAD。
期望 0 MISMATCH / 0 DEAD；UNKNOWN 是低置信不是错，但持续增长要查。
共享 URL（≥3 条记录共用）属合法形态，单独预警走 `shared_url_watch.py`。
