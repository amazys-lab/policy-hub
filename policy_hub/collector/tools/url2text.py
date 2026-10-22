"""url2text —— HTML → 正文文本 + 附件清单。

用法：
    python -m policy_hub.collector.tools.url2text page.html [--links] [--max N]
    python -m policy_hub.collector.tools.url2text https://... [--max N]   # 自动抓取

解决的三类真实事故（docs/agent/06-fetching.md）：
1. `text[:N]` 直接当正文 → 长导航吃满窗口、文号在窗外、分类器判「未归类」
   → 本工具按「剥 script/style/nav/header/footer/aside，取最大文本块」抽正文。
2. TRS 站附件不在 DOM `<a href>`，在内联 `var apps = [{name,url},…]`
   → 正则直抽，附在输出末尾。
3. 扫描版 PDF 文本层为 0 → 本工具只处理 HTML；PDF 请另行检测文本层。
"""
from __future__ import annotations

import argparse
import re
import sys

from .fetch_url import fetch_url

# TRS 系政务站内联附件
_PAT_APPS = re.compile(
    r'\{\s*name\s*:\s*"([^"]*)"\s*,\s*url\s*:\s*"([^"]*)"\s*\}')
_STRIP_TAGS = re.compile(r"<[^>]+>")
_COLLAPSE = re.compile(r"[ \t\r\f\v]+")


_PAT_DOCNO = re.compile(r"[〔\[]20\d\d[〕\]]\s*\d+\s*号")   # 公文文号特征


def _block_score(t: str) -> int:
    """块评分：长度为基，文号特征强加分，目录式列表（行多且每行极短）降权。"""
    score = len(t)
    if _PAT_DOCNO.search(t):
        score += 2000
    lines = [x for x in t.split("\n") if x.strip()]
    if len(lines) >= 8:
        avg = sum(len(x) for x in lines) / len(lines)
        if avg < 15:
            score //= 4          # 导航/栏目目录：一堆短行
    return score


def _readable_text(html: str) -> str:
    """去 script/style 后按块级标签切分，取评分最高的连续块为主正文。"""
    import html as _h
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<(nav|header|footer|aside)[^>]*>.*?</\1>", " ", html)
    blocks = re.split(r"(?i)</(?:p|div|li|tr|h[1-6]|section|article|td)>", html)
    best, best_score, cur, cur_score = [], 0, [], 0
    for b in blocks:
        t = _COLLAPSE.sub(" ", _h.unescape(_STRIP_TAGS.sub(" ", b))).strip()
        if not t:
            if cur_score > best_score:
                best, best_score = cur, cur_score
            cur, cur_score = [], 0
            continue
        cur.append(t)
        cur_score += _block_score(t)
    if cur_score > best_score:
        best, best_score = cur, cur_score
    return "\n".join(best)


def html_to_text(html: str) -> tuple[str, list[tuple[str, str]]]:
    """返回 (正文文本, [(附件名, url)])。"""
    text = _readable_text(html)
    # 兜底：主块太短时给全文去噪版（宁可多给上下文，别静默丢）
    if len(text) < 300:
        full = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
        text = _COLLAPSE.sub(" ", _STRIP_TAGS.sub(" ", full)).strip()
    atts = list(_PAT_APPS.findall(html))
    for u, inner in re.findall(
            r'<a[^>]+href="([^"]+\.(?:pdf|docx?|xlsx?|zip))"[^>]*>(.*?)</a>',
            html, re.I | re.S):
        atts.append((_strip(inner), u))
    return text, atts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="HTML 文件路径或 URL")
    ap.add_argument("--max", type=int, default=6000, help="正文截断长度")
    ap.add_argument("--links", action="store_true", help="附带正文内链接")
    a = ap.parse_args(argv)

    if a.src.startswith("http"):
        code, body = fetch_url(a.src)
        if code != 200:
            print(f"fetch failed: status={code}", file=sys.stderr)
            return 1
        for enc in ("utf-8", "gb18030"):
            try:
                html = body.decode(enc)
                break
            except UnicodeDecodeError:
                html = body.decode(enc, "ignore")
        else:
            html = body.decode("utf-8", "ignore")
    else:
        html = open(a.src, encoding="utf-8", errors="ignore").read()

    text, atts = html_to_text(html)
    out = text[:a.max]
    if len(text) > a.max:
        out += f"\n…[截断，全文 {len(text)} 字]"
    if atts:
        out += "\n\n[附件]\n" + "\n".join(f"- {n or '(无名)'}  {u}" for n, u in atts)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
