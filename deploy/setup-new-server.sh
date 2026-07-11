#!/bin/bash
# CycleBubble 一键初始化脚本 - 适用任何新 Linux 服务器
# 适用系统：Alibaba Cloud Linux 3 / CentOS / RHEL / Ubuntu / Debian
# 用法：
#   1. clone 仓库后 cd CycleBubble
#   2. cp deploy/env.example .env && vim .env  (填入密钥)
#   3. sudo bash deploy/setup-new-server.sh
set +e

set -o pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

[[ $EUID -ne 0 ]] && fail "请用 root 运行：sudo bash $0"

# 0. 检查 .env
[[ ! -f .env ]] && fail ".env 不存在！请先 cp deploy/env.example .env 并填入密钥"

# 1. 检测包管理器
if command -v dnf >/dev/null 2>&1; then
    PKG="dnf install -y"
elif command -v yum >/dev/null 2>&1; then
    PKG="yum install -y"
elif command -v apt >/dev/null 2>&1; then
    PKG="apt install -y"
else
    fail "未找到 dnf/yum/apt"
fi

info "使用包管理器：$PKG"

# 2. 安装基础依赖
info "=== 安装基础依赖 ==="
if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
    $PKG python3.11 python3.11-pip python3.11-devel git firewalld policycoreutils-python-utils sqlite 2>&1 | tail -3
elif command -v apt >/dev/null 2>&1; then
    apt update
    $PKG python3.11 python3-pip python3-venv git ufw sqlite3 2>&1 | tail -3
fi

# 3. 启动防火墙
info "=== 启动防火墙 ==="
if systemctl list-unit-files | grep -q firewalld; then
    systemctl enable --now firewalld
    firewall-cmd --permanent --add-service=http
    firewall-cmd --permanent --add-service=https
    firewall-cmd --permanent --add-service=ssh
    firewall-cmd --reload
elif systemctl list-unit-files | grep -q ufw; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw --force enable
fi

# 4. 准备应用目录
info "=== 准备应用目录 ==="
mkdir -p /var/www/app /var/www/frontend /var/log/app /etc/cyclebubble

# 5. clone 仓库（如果还没有）
if [[ ! -d /var/www/app/.git ]]; then
    info "=== clone 仓库 ==="
    # 默认仓库地址，可通过环境变量覆盖
    REPO_URL=${REPO_URL:-https://github.com/qiandkk/CycleBubble.git}
    git clone "$REPO_URL" /var/www/app
fi

cd /var/www/app || fail "cd /var/www/app 失败"

# 6. 创建虚拟环境
info "=== 创建 Python 虚拟环境 ==="
if [[ ! -d venv ]]; then
    python3.11 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip --quiet

# 7. 安装依赖
info "=== 安装 Python 依赖 ==="
pip install -r requirements.txt --quiet 2>&1 | tail -3

# 8. 读取 .env 注入到 systemd service
info "=== 配置 systemd 服务 ==="
JWT_SECRET=$(grep -E '^CB_JWT_SECRET=' .env | cut -d= -f2-)
ADMIN_PW=$(grep -E '^CB_ADMIN_PASSWORD=' .env | cut -d= -f2-)
DB_URL=$(grep -E '^CB_DATABASE_URL=' .env | cut -d= -f2-)
WH_SECRET=$(grep -E '^CB_GITHUB_WEBHOOK_SECRET=' .env | cut -d= -f2-)

[[ -z "$JWT_SECRET" ]] && fail ".env 里 CB_JWT_SECRET 不能为空"
[[ -z "$ADMIN_PW" ]]   && fail ".env 里 CB_ADMIN_PASSWORD 不能为空"
[[ -z "$WH_SECRET" ]]  && fail ".env 里 CB_GITHUB_WEBHOOK_SECRET 不能为空"

# 写 webhook secret 文件
echo -n "$WH_SECRET" > /etc/cyclebubble-webhook-secret
chmod 600 /etc/cyclebubble-webhook-secret
chown root:root /etc/cyclebubble-webhook-secret

# 写后端 service
sed -e "s|^Environment=\"CB_JWT_SECRET=.*|Environment=\"CB_JWT_SECRET=${JWT_SECRET}\"|" \
    -e "s|^Environment=\"CB_ADMIN_PASSWORD=.*|Environment=\"CB_ADMIN_PASSWORD=${ADMIN_PW}\"|" \
    deploy/systemd/cyclebubble-api.service > /etc/systemd/system/cyclebubble-api.service

cp deploy/systemd/cyclebubble-webhook.service /etc/systemd/system/

# 9. 部署 webhook 接收端 + 自动更新脚本 + watchdog
info "=== 部署 webhook + 自动更新脚本 ==="
cp deploy/scripts/cyclebubble-webhook.py /usr/local/bin/cyclebubble-webhook.py
chmod 755 /usr/local/bin/cyclebubble-webhook.py

cp deploy/scripts/cyclebubble-update.sh /usr/local/bin/cyclebubble-update.sh
chmod 755 /usr/local/bin/cyclebubble-update.sh

cp deploy/scripts/webhook-watchdog.sh /usr/local/bin/webhook-watchdog.sh
chmod 755 /usr/local/bin/webhook-watchdog.sh

# 10. 部署前端
info "=== 部署前端文件 ==="
cp -f index.html styles.css script.js api.js /var/www/frontend/
chown -R www:www /var/www/frontend /var/www/app
chmod 755 /var/www/frontend /var/www/app
find /var/www/frontend -type f -exec chmod 644 {} +
find /var/www/app -type f -not -path "*/venv/*" -not -path "*/.git/*" -exec chmod 644 {} +

# 11. 配置 nginx（尝试宝塔和标准位置）
info "=== 配置 nginx ==="
if [[ -d /www/server/panel/vhost/nginx ]]; then
    # 宝塔面板
    cp deploy/nginx-mysite.conf /www/server/panel/vhost/nginx/mysite.conf
    [[ -f /www/server/panel/vhost/nginx/default.conf ]] && \
        mv /www/server/panel/vhost/nginx/default.conf /www/server/panel/vhost/nginx/default.conf.bak
    info "检测到宝塔面板，已写入 /www/server/panel/vhost/nginx/mysite.conf"
else
    # 标准 nginx
    cp deploy/nginx-mysite.conf /etc/nginx/conf.d/mysite.conf
    info "已写入 /etc/nginx/conf.d/mysite.conf"
fi

nginx -t && nginx -s reload || warn "nginx reload 失败，请检查配置"

# 12. 启动服务
info "=== 启动 systemd 服务 ==="
systemctl daemon-reload
systemctl enable cyclebubble-api cyclebubble-webhook
systemctl restart cyclebubble-api cyclebubble-webhook
sleep 3

# 13. 注册 watchdog cron
info "=== 注册 watchdog cron ==="
(crontab -l 2>/dev/null | grep -v webhook-watchdog; echo "* * * * * /usr/local/bin/webhook-watchdog.sh") | crontab -

# 14. 开放 webhook 端口（firewalld 层）
if systemctl list-unit-files | grep -q firewalld; then
    firewall-cmd --permanent --add-port=9000/tcp
    firewall-cmd --reload
    info "已开放 9000/tcp (firewalld)"
fi

# 15. 验证
info "=== 验证部署 ==="
sleep 2
echo -n "  /api/health: "
curl -s -m 5 http://127.0.0.1:8000/api/health -w "  HTTP:%{http_code}\n" 2>/dev/null || echo "FAILED"
echo -n "  webhook health: "
curl -s -m 5 http://127.0.0.1:9000/health -w "  HTTP:%{http_code}\n" 2>/dev/null || echo "FAILED"
echo -n "  主页: "
curl -s -o /dev/null -m 5 -w "HTTP:%{http_code} 大小:%{size_download}B\n" http://127.0.0.1/

info ""
info "================================================"
info "✅ 部署完成！"
info "================================================"
info "下一步需要做："
info "1. 阿里云 ECS 控制台 → 安全组 → 入方向放行端口 22, 80, 443, 9000"
info "2. GitHub 仓库 → Settings → Webhooks → 添加："
info "     URL:    http://YOUR_SERVER_IP:9000/webhook"
info "     Secret: ${WH_SECRET:0:8}...（共 ${#WH_SECRET} 字符）"
info "     Event:  Just the push event"
info "3. 跑一次 seed_demo 填演示数据："
info "     cd /var/www/app && source venv/bin/activate"
info "     CB_JWT_SECRET='$JWT_SECRET' CB_ADMIN_PASSWORD='$ADMIN_PW' python -m backend.seed_demo --reset"