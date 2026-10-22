"""search_site —— 站内候选发现：Bing `site:` 检索，返回标题+链接。

用法：
    python -m policy_hub.collector.tools.search_site <host> <关键词...> [--pages 2]

示例：
    python -m policy_hub.collector.tools.search_site fuzhou.gov.cn 人才 补贴 办法

输出：JSON 数组 [{title, url, snippet}]（stdout），进度打 stderr。
定位：候选发现层（「本月这座城新发了什么」的起点）——结果仍须逐条
fetch + classify + 人工开正文核对，本工具不判真伪。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse

from .fetch_url import fetch_url, UA

_RES = re.compile(
    r'<h2[^>]*><a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a></h2>.*?'
    r'(?:<p[^>]*>(.*?)</p>)?', re.S)
_DDG_RES = re.compile(
    r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
    r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
_BD_RES = re.compile(
    r'<h3[^>]*>\s*<a[^>]+href="(http[^"]+)"[^>]*>(.*?)</a>', re.S)


def _strip(s: str) -> str:
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def _bing(host: str, q: str, first: int) -> list[dict]:
    url = f"https://cn.bing.com/search?q={q}&first={first}&setlang=zh-CN&mkt=zh-CN"
    code, body = fetch_url(url, referer="https://cn.bing.com/")
    if code != 200:
        print(f"  bing status={code}", file=sys.stderr)
        return []
    html = body.decode("utf-8", "ignore")
    out = []
    for m in _RES.finditer(html):
        u, title, snip = m.group(1), _strip(m.group(2)), _strip(m.group(3) or "")
        out.append({"title": title, "url": u, "snippet": snip[:160]})
    return out


def _baidu(host: str, q: str) -> list[dict]:
    url = f"https://www.baidu.com/s?wd={q}&rn=20"
    code, body = fetch_url(url, referer="https://www.baidu.com/")
    if code != 200:
        print(f"  baidu status={code}", file=sys.stderr)
        return []
    html = body.decode("utf-8", "ignore")
    out = []
    for m in _BD_RES.finditer(html):
        u, title = m.group(1), _strip(m.group(2))
        if u.startswith("http"):
            out.append({"title": title, "url": u, "snippet": ""})
    return out


def search(host: str, keywords: list[str], pages: int = 2) -> list[dict]:
    q = urllib.parse.quote(f"site:{host} " + " ".join(keywords))
    out, seen = [], set()
    for page in range(pages):
        rows = _bing(host, q, 1 + page * 10)
        if page == 0:
            in_host = any(host in urllib.parse.urlparse(r["url"]).netloc
                          for r in rows)
            if rows and not in_host:
                # Bing 对收录少的站会无视 site: 泛化结果（Baidu 另有验证墙）
                print("  提示：引擎未遵守 site: 限定（该站收录少）。"
                      "建议改用目标站自带搜索接口（站内搜索 > 全网搜）。",
                      file=sys.stderr)
                rows += _baidu(host, q)
        for r in rows:
            u = r["url"]
            if u in seen or host not in urllib.parse.urlparse(u).netloc:
                continue
            seen.add(u)
            out.append(r)
        time.sleep(1.5)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("host", help="限定域名，如 rst.fujian.gov.cn")
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--pages", type=int, default=2)
    a = ap.parse_args(argv)
    rows = search(a.host, a.keywords, a.pages)
    print(f"共 {len(rows)} 条候选", file=sys.stderr)
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
