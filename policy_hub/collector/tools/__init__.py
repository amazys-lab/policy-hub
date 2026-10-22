"""采集工具箱：可组合的小工具，供 agent / 人工在采集批次中现场组合使用。

- fetch_url    抓单个 URL（UA/Referer/退避/curl 兜底），存文件或打 stdout
- url2text     HTML → 正文文本（剥导航/页脚/侧栏）+ 附件抽取（TRS var apps）
- search_site  站内候选发现（Bing site: 检索，返回标题+链接 JSON）

设计原则：只做确定性零件；「去哪找、找什么」的智能判断由调用方（agent）承担。
"""
