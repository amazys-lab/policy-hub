# -*- coding: utf-8 -*-
"""PolicyHub 一键启动器
------------------------------------------------------------------
用法：python run.py [--port 8000] [--rebuild-db]

行为：
  1) 探测一个装好 fastapi/uvicorn 的 Python 解释器（优先当前解释器）。
  2) server/policy.db 不存在（或 --rebuild-db）→ 先跑 server.publish_db
     生成版本化数据库（内含统一体检，闸门不过会中止）。
  3) 启动 FastAPI 服务，浏览器打开 http://127.0.0.1:<port>/
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(ROOT, "server", "policy.db")


def ensure_deps():
    """确认 fastapi/uvicorn 可导入；不行则提示安装（不代装，保持环境可控）。"""
    try:
        import fastapi, uvicorn  # noqa: F401
        return
    except ImportError:
        print("缺少依赖：fastapi / uvicorn。请先执行：")
        print("    pip install -r requirements.txt")
        sys.exit(1)


def ensure_db(rebuild=False):
    if os.path.exists(DB) and not rebuild:
        return
    if not rebuild:
        print("== 未发现 server/policy.db：直接以源库模式启动（data_version=v-source）==")
        print("   空库不生成版本化 DB；接入数据后如需生成请加 --rebuild-db")
        return
    print("== 首次运行：生成版本化数据库（含统一体检，可能需要 1-3 分钟）==")
    r = subprocess.run([sys.executable, "-m", "server.publish_db", "run.py 首次生成"],
                       cwd=ROOT)
    if r.returncode != 0:
        print("!! 数据库生成失败（见上方体检输出）→ 已中止。")
        sys.exit(r.returncode or 1)


def main():
    # 端口优先级：--port 参数 > PORT 环境变量 > 8000。
    # 部署平台（容器/PaaS）通常注入 PORT 环境变量，必须读取，否则服务起在固定端口会被平台判死。
    port = int(os.environ.get("PORT", 8000))
    rebuild = False
    args = sys.argv[1:]
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    rebuild = "--rebuild-db" in args

    ensure_deps()
    ensure_db(rebuild)

    print("=" * 56)
    print("  PolicyHub 已启动:  http://127.0.0.1:%d/" % port)
    print("  API 文档:          http://127.0.0.1:%d/docs" % port)
    print("  停止服务:          Ctrl+C")
    print("=" * 56)
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=port,
                log_level="info")


if __name__ == "__main__":
    main()
