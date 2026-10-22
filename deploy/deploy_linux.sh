#!/usr/bin/env bash
# ============================================================
# 深圳政策匹配系统 · Linux 一键部署脚本（Ubuntu 22.04/24.04 验证思路）
# 用法：把整个项目上传到服务器后，在项目根目录执行  bash deploy/deploy_linux.sh
# 幂等：可重复执行，用于首次部署和后续更新
# ============================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="policy-hub"
SERVICE="/etc/systemd/system/${APP_NAME}.service"

echo ">> 项目目录：${APP_DIR}"

# 1) 系统依赖（python3-venv 建虚拟环境，nginx 反代）
if ! command -v python3 >/dev/null; then sudo apt-get update && sudo apt-get install -y python3 python3-venv; fi
sudo apt-get install -y nginx

# 2) 虚拟环境 + Python 依赖
cd "${APP_DIR}"
if [ ! -d ".venv" ]; then python3 -m venv .venv; fi
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

# 3) 发布最新政策库到 SQLite（生成/更新 server/policy.db 的最新版本）
./.venv/bin/python -m server.publish_db "上云部署发布"

# 4) systemd 常驻（uvicorn 只监听 127.0.0.1:8000）
sudo cp "${APP_DIR}/deploy/${APP_NAME}.service" "${SERVICE}"
sudo sed -i "s#/opt/policy-hub#${APP_DIR}#g" "${SERVICE}"
# 让 www-data 能读项目目录（如目录在 /root 下请改放到 /opt 或 /srv）
sudo chown -R www-data:www-data "${APP_DIR}" || true
sudo systemctl daemon-reload
sudo systemctl enable ${APP_NAME}
sudo systemctl restart ${APP_NAME}

# 5) Nginx 配置（仅在未配置时安装，避免覆盖你已改过的文件）
NGX="/etc/nginx/sites-available/${APP_NAME}"
if [ ! -f "${NGX}" ]; then
  sudo cp "${APP_DIR}/deploy/nginx_policyhub.conf" "${NGX}"
  sudo ln -sf "${NGX}" /etc/nginx/sites-enabled/${APP_NAME}
  sudo rm -f /etc/nginx/sites-enabled/default
fi
sudo nginx -t && sudo systemctl reload nginx

# 6) 防火墙：只开 22/80/443，8000 不对公网开放
sudo ufw allow 22/tcp  || true
sudo ufw allow 80/tcp  || true
sudo ufw allow 443/tcp || true

echo ""
echo ">> 部署完成。自检："
echo "   systemctl status ${APP_NAME}          # 后端状态"
echo "   curl -s http://127.0.0.1:8000/api/v1/meta   # 本机接口"
echo ">> 下一步：域名解析到本机 → certbot --nginx 上 HTTPS（见《上云部署手册》）"
