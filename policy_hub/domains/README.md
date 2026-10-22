# 数据目录

**本仓不附带任何政策数据。** 这个目录只有结构，政策条目由你采集后按下面的规则填进来。

引擎、字段契约、校验闸门、成品导出全部可独立运行；数据是你自己的资产，不随本仓分发。

## 目录结构

```
policy_hub/domains/
└── cities/
    └── <城市码小写>/
        └── <域英文名>/
            ├── programs.json    # 该域的政策条目（money / review 型）
            └── channels.json    # 该域的申报通道（channel 型，主要用 hukou）
```

城市码见 `policy_hub/common/schema.json` 的 `city_code`（已登记 51 个常见城市，两字母大写；目录名用小写）。
要新增城市，跑 `pipeline/register_city_codes.py`，别手改——城市码有 5 个注册点，漏一个就会在界面上静默消失。

## 九个域

| 目录名 | 中文名 | 结果类型 | 主要文件 |
|---|---|---|---|
| `employment_startup` | 就业创业补贴 | money | programs.json |
| `enterprise_support` | 企业用工扶持 | money | programs.json |
| `tech_enterprise` | 科技企业扶持 | money | programs.json |
| `vocational_training` | 职业技能培训 | money | programs.json |
| `inclusive_tax` | 普惠税费减免 | money | programs.json |
| `housing` | 人才安居住房 | channel | programs.json |
| `hukou` | 落户通道 | channel | channels.json + programs.json |
| `gba_tax` | 大湾区个税补贴 | money | programs.json |
| `overseas` | 人才引进 | review | programs.json |

`gba_tax` 有明文地域限制（只对大湾区 9 市有意义），所以 `register_city_codes.py` 给新城市
默认只声明 8 个域、不含它。大湾区城市要单独声明（`EXCLUSIVE_DOMAINS` 白名单里已列了
广州/深圳/珠海/佛山/惠州/东莞/中山/江门/肇庆，加这 9 市之外的城市不要声明 `gba_tax`）。

## 填一个城市需要四步

1. **登记城市码**（已登记过的跳过）

   在 `pipeline/register_city_codes.py` 顶部的 `NEW` 列表里加一行：
   `("SZ", "深圳市", "深圳", "广东")` —— 依次是城市码、全名、前端简称、省份。
   然后执行（不带 `--apply` 只是预演，不落盘）：
   ```
   python pipeline/register_city_codes.py --apply
   ```

2. **从模板复制**
   ```
   mkdir -p policy_hub/domains/cities/<城市码小写>/<域英文名>
   cp policy_hub/templates/new_city/programs.template.json \
      policy_hub/domains/cities/<城市码小写>/<域英文名>/programs.json
   ```

3. **逐条替换**。模板开头的 `_填写说明` 写清了必填字段和几条铁律：
   - 每条必须带官方文号 + `*.gov.cn` 原文链接，第三方站点只作线索
   - 金额单位是元、用阿拉伯数字
   - 达不到 L4 就诚实标 `depth` 并在 `to_collect` 写明缺什么，不要用印象补齐
   - ID 形如 `XX-EMP-001`（`XX` 为城市码），全局唯一，删掉的号不复用
   - **`cond.applicant_kinds` 必须写全「谁能领」**。界面上四张画像（个人求职者 / 企业单位 /
     自主创业者 / 海外留学人才）各自只认自己那一个值，写漏哪张，那张画像的客户就看不到这条政策，
     而且**不会有任何报错**。创业补贴尤其容易写漏：
     | 实际情况 | 该写什么 |
     |---|---|
     | 只有个人（含灵活就业、失业人员）能领 | `["person"]` |
     | 只有创业者 / 个体户 / 法人能领 | `["entrepreneur"]` |
     | 个人和创业者都能领 | `["person","entrepreneur"]` ← 创业补贴最常见 |
     | 单位 / 企业能领 | `["unit"]` |
     | 单位和个人都能领 | `["person","unit"]` |
     | 只给留学 / 海外人才 | `["overseas"]` |
     | 海外人才和个人都能领 | `["person","overseas"]` |

     引擎唯一的内置展开：选「海外人才」画像时，标 `person` 的政策也算命中（海外人才首先是个"人"）；
     反向不成立 —— 选「个人」画像不会吃到只给海外人才的政策。

4. **校验**
   ```
   python pipeline/check_data.py               # 字段契约 + 枚举 + ID 唯一性
   python -m policy_hub.aggregator.aggregate   # 引擎自检（会打印当前条数）
   ```

5. **重启服务就能看到**
   ```
   python run.py
   ```
   城市下拉里的城市清单**由数据现算**（`/api/v1/meta`），不用改前端、不用重新生成任何文件。
   重启后下拉里就多出这座城；没数据时它会出现在下拉里但结果是空的 —— 这是正常的。

## 出成品

```
# B 端（机构/决策者全量表，24 列）：--cities 可多城
python pipeline/export_excel.py --audience b --cities SZ,NN --title "深圳南宁政策总表" --out out.xlsx

# C 端（个人读者清单，20 列）：单城用 --preset city_<城市码小写>
python pipeline/export_excel.py --audience c --preset city_yb --out out_c.xlsx

# 改完数据对一遍账：每份成品该有多少条、哪份缺了（只读，不写文件）
python pipeline/release_matrix.py
```

两个容易踩的点：

- **C 端不认 `--cities`**，只认 `--preset city_<码>`（多城用 `prd` / `all`）。写 `--cities` 会直接报错。
- **0 条不出空表**：范围里没有现行有效政策时，导出会报错退出而不是生成一个只有表头的文件。
  `--preset all` / `c_all` 会自动带上你新加的城市；`gd` / `prd` 是固定珠三角名册，不会自动加。

## 数据为空是正常状态

新克隆的仓库这里只有结构文件。此时：

- `python -m policy_hub.aggregator.aggregate` 会打印「当前库中 0 条」，不是报错
- 网页和 API 能正常启动，城市下拉为空并提示「尚无数据」
- 出成品（Excel）会因为没有数据而拒绝执行，而不是生成空文件

填进第一批数据后，上述命令就会开始返回真实结果。
