# 政策智能匹配系统 · 阶段A（本机可运行的后端 + API）

> 把单文件 Demo 升级为"前端调接口、数据版本化、可持续更新"的线上系统雏形。
> 匹配引擎直接复用 `policy_hub`（已通过画像回归），本层只做对外服务，不重写规则。

## 一、目录与职责
```
server/
  publish_db.py    数据发布：把审核后的 policy_hub/domains/*.json 版本化写入 policy.db
  policy.db        SQLite 发布库（运行 publish_db 后生成；线上只读最新版本）
  app.py           FastAPI 只读接口：/meta /match /checklist /policy/{id}
  static/demo_api.html  前后端分离联调演示页（不内嵌数据，全部走接口）
```

## 二、本机启动（项目根目录，三步）
```powershell
# 1) （首次或政策更新后）把结构化库发布成一个数据版本
python -m server.publish_db "版本备注，可选"

# 2) 启动 API 服务
python -m uvicorn server.app:app --port 8000

# 3) 浏览器打开
#    http://127.0.0.1:8000/                 联调演示页（自动跳 static/demo_api.html）
#    http://127.0.0.1:8000/docs             Swagger 接口文档，可在线点 Try 调试
#    http://127.0.0.1:8000/api/v1/meta       元信息
```
依赖：`pip install fastapi uvicorn`（uvicorn 本机已具备）。改了 app.py 加 `--reload` 自动重启。

## 三、四个接口
| 接口 | 方法 | 入参 | 作用 |
|---|---|---|---|
| /api/v1/meta | GET | — | 数据版本、发布时间、三域条数、留学覆盖区 |
| /api/v1/match | POST | `{profile:{...}}` | 统一画像→三域匹配，返回 summary + 各域命中（含金额、简要元数据） |
| /api/v1/checklist | POST | `{profile,brand}` | 生成可复制个性化清单文本，brand 传 {company,contact} 即贴牌 |
| /api/v1/policy/{id} | GET | — | 取单条完整政策（材料/步骤/时效/官方源/版本） |

画像字段沿用 `policy_hub/common/schema.json -> unified_profile`，空字段引擎自动给默认值，空画像不报错。

## 四、数据怎么更新（巡检→发布的闭环）
1. `python -m policy_hub.collector.run_inspection --mode offline/online/import` 出巡检报告；
2. 人工回官方源核实，改 `policy_hub/domains/*.json`（version+1、updated_at、source_doc）；
3. 跑 `python policy_hub/aggregator/aggregate.py` 回归必须全绿；
4. `python -m server.publish_db "本次更新说明"` → 生成新 data_version；
5. 重启服务即生效；policy.db 里保留全部历史版本，可回溯（也是数据资产登记/举证材料）。

## 五、上云（阶段A验证通过后）
1. 买一台轻量应用服务器（选离客户近的地域，2 核 2G 足够），装 Python；
2. 上传本项目，`pip install -r requirements`，用 `uvicorn server.app:app --host 0.0.0.0 --port 8000`；
3. 前置 Nginx + HTTPS + 域名（国内服务器绑定域名需 ICP 备案；先用公网IP可快速演示）；
4. 用 systemd/进程守护让其常驻；collector 用 cron 周期跑。
（详见项目根《线上系统建设方案.md》阶段B/C：多租户贴牌、运营后台、开放计费API、扩城。）

## 六、合规（写死在出参层）
- 所有返回带 data_version 与免责声明；金额/积分为规则估算，以官方最新文件及窗口审核为准；
- review/competition（评审/积分排序）只做资格预判，不承诺入选/通过；
- 线上只通过接口返回匹配结果，不整份下发结构化库，防白嫖。
