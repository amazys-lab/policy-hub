"""fetch_url —— 抓单个 URL，带 UA / Referer / 退避重试 / curl 兜底。

用法：
    python -m policy_hub.collector.tools.fetch_url <url> [-o out.html]
        [--referer https://host/] [--timeout 30] [--retries 3] [--method get|curl]

输出：stderr 打状态行（status/bytes/耗时），正文写 -o 文件或 stdout。
退出码：0 成功；1 全部尝试失败（打印最后一次错误）。

经验内建（详见 docs/agent/06-fetching.md）：
- Referer 是多数政务 WAF 的钥匙：403/412 时自动带 `Referer: https://<host>/` 重试。
- 判死只有 404/410；403/412/502/000 都是故障。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# 故障类状态码：换姿势重试，不当死链
RETRYABLE = {0, 403, 412, 429, 500, 502, 503, 504}
DEAD = {404, 410}


def _curl(url: str, referer: str | None, timeout: int) -> tuple[int, bytes]:
    cmd = ["curl", "-sL", "--compressed", "-A", UA,
           "-H", "Accept-Language: zh-CN,zh;q=0.9",
           "--max-time", str(timeout), "-w", "%{http_code}", url]
    if referer:
        cmd[2:2] = ["-H", f"Referer: {referer}"]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout + 10)
    body, code = p.stdout[:-3], p.stdout[-3:]
    try:
        return int(code), body
    except ValueError:
        return 0, b""


def fetch_url(url: str, referer: str | None = None, timeout: int = 30,
              retries: int = 3) -> tuple[int, bytes]:
    """返回 (status, body)。status=0 表示连接层失败。"""
    import requests
    import urllib3
    urllib3.disable_warnings()
    auto_referer = referer
    last = (0, b"")
    for i in range(retries):
        headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
        if auto_referer:
            headers["Referer"] = auto_referer
        # 每轮两条腿：requests（快）→ 失败/被拦即 curl（TLS 指纹不同，常能过 WAF）
        try:
            r = requests.get(url, headers=headers, timeout=timeout,
                             allow_redirects=True, verify=False)
            code, body = r.status_code, r.content
        except Exception:
            code, body = 0, b""
        if code != 200:
            c2, b2 = _curl(url, auto_referer, timeout)
            if c2 == 200 or not code:
                code, body = c2, b2
        if code == 200:
            return code, body
        last = (code, body)
        if code in DEAD:
            return code, body          # 死链不重试
        if code in RETRYABLE and auto_referer is None:
            auto_referer = "https://" + url.split("/")[2] + "/"   # WAF 钥匙
        time.sleep(min(2 ** i, 8))
    return last


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("-o", "--out", help="写入文件（缺省打 stdout）")
    ap.add_argument("--referer")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args(argv)
    t0 = time.time()
    code, body = fetch_url(a.url, a.referer, a.timeout, a.retries)
    dt = time.time() - t0
    print(f"status={code} bytes={len(body)} elapsed={dt:.1f}s url={a.url}",
          file=sys.stderr)
    if code != 200:
        return 1
    if a.out:
        with open(a.out, "wb") as f:
            f.write(body)
        print(a.out, file=sys.stderr)
    else:
        sys.stdout.buffer.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
