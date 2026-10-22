#!/usr/bin/env bash
# 服务器初始化（Ubuntu 22.04/24.04），在新服务器上以 root 执行一次：
#   curl -fsSL <仓库 raw 地址>/deploy/server_init.sh | sudo bash -s -- <部署用户名> "<部署公钥>" [single-server]
# 第三个参数为 single-server 时（测试与生产共用一台服务器）额外开放测试环境网关端口 18000。
# 注意：部署用户属于 docker 组，等同于服务器 root。单服务器方案中测试环境的部署密钥同样能访问生产数据，
# 因此 test 环境只允许 main 分支使用（scripts/github_setup.sh）；需要更强隔离时测试与生产使用不同服务器。
# 之后所有部署都由流水线完成，不在服务器上手工操作。
set -euo pipefail

DEPLOY_USER="${1:-deploy}"
DEPLOY_PUBKEY="${2:-}"
LAYOUT="${3:-two-servers}"

# Docker（官方 apt 源）
if ! command -v docker > /dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi

# 部署用户：只能通过密钥登录，属于 docker 组
id "$DEPLOY_USER" > /dev/null 2>&1 || useradd -m -s /bin/bash "$DEPLOY_USER"
usermod -aG docker "$DEPLOY_USER"
if [[ -n "$DEPLOY_PUBKEY" ]]; then
  install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
  echo "$DEPLOY_PUBKEY" >> "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
  chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
  # 已配置公钥后关闭密码登录
  install -d /etc/ssh/sshd_config.d
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\n' > /etc/ssh/sshd_config.d/90-campus.conf
  systemctl reload ssh 2> /dev/null || systemctl reload sshd 2> /dev/null || true
fi

install -d -o "$DEPLOY_USER" -g "$DEPLOY_USER" /opt/campus

# 每日 03:00 备份各环境数据库（deploy.sh 把 backup.sh 放在 /opt/campus/<环境>/ 下）
cat > /etc/cron.d/campus-backup <<CRON
0 3 * * * $DEPLOY_USER for d in /opt/campus/*/; do [ -x "\$d/backup.sh" ] && "\$d/backup.sh" daily >> "\$d/backup.log" 2>&1; done
CRON
chmod 644 /etc/cron.d/campus-backup

# 防火墙：只开放 SSH 和网关端口（两台服务器方案用 8000；单服务器方案测试环境另开 18000）。
# 注意 Docker 发布的端口会绕过 ufw，所以 compose 中除网关外的端口一律只绑定 127.0.0.1。
if command -v ufw > /dev/null; then
  ufw allow OpenSSH
  ufw allow 8000/tcp
  if [[ "$LAYOUT" == "single-server" ]]; then ufw allow 18000/tcp; fi
  ufw --force enable
fi

echo "服务器初始化完成：docker $(docker --version | awk '{print $3}')，部署目录 /opt/campus"
