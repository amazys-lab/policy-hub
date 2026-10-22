# MCP Server

把政策库包成 AI agent 可直接调用的工具。Claude Code、Cursor、WorkBuddy、Codex
这类支持 MCP 的客户端，接上之后就能用自然语言查政策、判资格、要材料清单。

## 为什么不是"把政策喂给大模型"

政策里的钱、期限、资格必须精确。"最高 3 万"和"最高 10 万"在语义检索里只差几个 token,
在窗口审核那里差一整笔钱。所以这里的工具**调用的是规则引擎**,不是让模型读原文后自由发挥 ——
模型负责理解用户、组织语言,判定和算钱交给代码。

## 两种后端

| 模式 | 触发条件 | 适用 |
|---|---|---|
| **本地** | 默认 | agent 和仓库在同一台机器,零配置 |
| **远程** | 设 `POLICY_HUB_URL`(+ 可选 `POLICY_HUB_KEY`) | 服务端部署一次,多台机器连过来 |

```bash
# 本地模式（什么都不用设）
python -m mcp_server.server

# 远程模式
set POLICY_HUB_URL=https://your-host          # Windows
set POLICY_HUB_KEY=ph_xxxxxxxx
python -m mcp_server.server
```

## 客户端配置

**Claude Code / Cursor**（`mcpServers`）：

```json
{
  "mcpServers": {
    "policy-hub": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "<本仓绝对路径>"
    }
  }
}
```

**WorkBuddy**：在 `~/.workbuddy/mcp.json` 的 `mcpServers` 里写同样的结构,
然后在连接器管理页对新服务器点「信任」—— MCP 配置改完不会自动生效。

远程模式把 `env` 带上：

```json
{
  "mcpServers": {
    "policy-hub": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "<本仓绝对路径>",
      "env": {
        "POLICY_HUB_URL": "https://your-host",
        "POLICY_HUB_KEY": "ph_xxxxxxxx"
      }
    }
  }
}
```

## 五个工具

| 工具 | 干什么 | 返回 |
|---|---|---|
| `search_policies` | 按城市 / 关键词 / 域找政策 | 摘要列表(不含正文) |
| `match_profile` | 按画像判能报哪些 | 分组结果 + 各组计数 |
| `get_policy` | 取单条全字段 | 金额规则、条件、材料、链接 |
| `get_checklist` | 生成可展示的清单文本 | 排版好的多行文本 |
| `list_profile_fields` | 列出画像可用字段及频次 | 字段 → 频次 |

**典型对话**：

> 用户:我 30 岁,本科,在 SZ 开了家小公司 2 年了,能领什么补贴?

agent 的动作序列:
1. `list_profile_fields()` → 知道有 `contract_years`、`ent_ss_months` 这些字段
2. `match_profile("SZ", "entrepreneur", {"age":30,"edu":"bachelor","biz_reg_months":24})`
3. 挑几条 `get_policy(...)` 看细节
4. `get_checklist(...)` 给客户一份能直接看的清单

## 返回值的两个约束

- **只回摘要**：`search_policies` 不返回正文,拿 id 再 `get_policy`。MCP 的返回值直接进对话
  上下文,一次塞几百条全文会把上下文打爆。
- **长文本截断**：`get_policy` 里超过 2000 字的字段会截断并在 `truncated_fields` 里列出字段名,
  需要全文时去读 `policy_hub/domains/` 原始 JSON。

## 已知局限

- 金额与资格均为**规则估算**,工具返回带 `disclaimer`,agent 不应替用户承诺结果。
- 远程模式下 `list_profile_fields` 只能给常用字段表(没有对应开放端点),频次需本地模式或
  直接调 `/api/v1/meta`。
- 本仓不带数据：没填之前 `search_policies` 返回 0 条是正常的。填多少取决于你采了多少，
  不是工具坏了。
