#!/usr/bin/env bash
# 部署到测试或生产服务器。
# 用法：scripts/deploy.sh <test|prod> <镜像标签>
#
# 需要的环境变量：
#   DEPLOY_HOST, DEPLOY_USER     SSH 目标（私钥已加载到 ssh-agent，主机指纹已写入 ~/.ssh/known_hosts）
#   REGISTRY, REGISTRY_USER, REGISTRY_TOKEN（只需拉取权限）
#   .env.example 中列出的密钥：取值顺序为同名环境变量（GitHub 环境 secrets）> 仓库根目录的 .env > .env.example 默认值；
#   标记为 @random-if-empty 且取值为空的密钥在服务器上首次部署时生成随机值并保留；其余为空的项不写入
#   ENV_FILE（可选）             默认 deploy/env/<env>.env；单服务器方案用 test-single-server.env
# 在 GitHub Actions 中运行时，把网关地址写入步骤输出 gateway_url。
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_NAME="$1"
VERSION="$2"
ENV_FILE="${ENV_FILE:-deploy/env/$ENV_NAME.env}"
REMOTE_DIR="/opt/campus/$ENV_NAME"
PROJECT="campus-$ENV_NAME"
TARGET="$DEPLOY_USER@$DEPLOY_HOST"
EXPECTED_SHA="$(git rev-parse "$VERSION^{commit}" 2> /dev/null || git rev-parse HEAD)"

port="$(grep '^GATEWAY_PORT=' "$ENV_FILE" | cut -d= -f2)"
gateway_url="http://$DEPLOY_HOST:$port"

umask 077 # 部署目录（含 .env 密钥）只对部署用户可读
generated=() # 需在服务器上生成随机值的密钥
random_if_empty=" $(sed -n 's/^# @random-if-empty: *//p' .env.example) "

# 读取 .env 中某个键的值（去掉两侧引号）；没有 .env 或没有该键时输出空并返回非零
env_file_value() {
  [[ -f .env ]] || return 1
  local line
  line="$(grep -E "^$1=" .env | tail -n 1)" || return 1
  line="${line#*=}"
  line="${line#[\"\']}"
  printf '%s' "${line%[\"\']}"
}
stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

# .env 中的值用单引号包裹：compose 对单引号内的内容不做变量替换、不识别注释，密钥按原样传入。
# 单引号本身无法在其中表示，含单引号的值直接拒绝（生成的密钥是十六进制，不含单引号）
quote() {
  if [[ "$1" == *"'"* ]]; then
    echo "::error::配置值不能包含单引号" >&2
    exit 1
  fi
  printf "'%s'" "$1"
}

# 1. 组装部署目录：compose、网关配置、数据库初始化与备份脚本、.env
cp deploy/docker-compose.yml "$stage/"
mkdir -p "$stage/gateway" "$stage/postgres"
cp deploy/gateway/gateway.conf deploy/gateway/upstreams.conf.template "$stage/gateway/"
cp deploy/postgres/init.sh "$stage/postgres/"
cp deploy/backup.sh "$stage/"
chmod 644 "$stage/docker-compose.yml" "$stage/gateway/"* # 容器内的非 root 进程需要读取挂载的配置
chmod 755 "$stage/postgres/init.sh" "$stage/backup.sh"
{
  cat "$ENV_FILE"
  emit() { local v; v="$(quote "$2")"; echo "$1=$v"; } # 赋值使 quote 的失败在 set -e 下生效
  emit REGISTRY "$REGISTRY"
  emit VERSION "$VERSION"
  while IFS= read -r line; do
    key="${line%%=*}"
    [[ -z "$key" || "$key" == \#* ]] && continue
    value="${!key:-}"
    [[ -n "$value" ]] || value="$(env_file_value "$key")" || value=""
    [[ -n "$value" ]] || value="${line#*=}"
    if [[ -n "$value" ]]; then
      emit "$key" "$value"
    elif [[ "$random_if_empty" == *" $key "* ]]; then
      generated+=("$key") # 在服务器上生成，见下方远程步骤
    fi
  done < .env.example
} > "$stage/.env"

# 2. 上传，备份数据库，启动。--wait 等所有服务健康后才返回，失败则整个部署失败
ssh "$TARGET" "mkdir -p $REMOTE_DIR && chmod 700 $REMOTE_DIR"
scp -rpq "$stage/." "$TARGET:$REMOTE_DIR/"
# 变量在本地展开后发送到服务器执行（有意为之）
# shellcheck disable=SC2087
ssh "$TARGET" bash -s << REMOTE
set -euo pipefail
cd $REMOTE_DIR
# 未提供的签名/认证密钥：首次部署时生成随机值并保留，之后每次部署沿用
touch .secrets.generated && chmod 600 .secrets.generated
for key in ${generated[*]:-}; do
  grep -q "^\$key=" .secrets.generated || echo "\$key='\$(openssl rand -hex 32)'" >> .secrets.generated
  grep "^\$key=" .secrets.generated >> .env
done
chmod 600 .env
trap 'docker logout "${REGISTRY%%/*}" > /dev/null 2>&1 || true' EXIT # 无论成败都不在服务器上留下仓库令牌
echo "$REGISTRY_TOKEN" | docker login "${REGISTRY%%/*}" -u "$REGISTRY_USER" --password-stdin > /dev/null
docker compose -p $PROJECT pull --quiet
# 迁移在 api 启动时执行，先备份（首次部署时数据库尚未运行，跳过）
./backup.sh pre-deploy-$VERSION
docker compose -p $PROJECT up -d --remove-orphans --wait --wait-timeout 300
echo "\$(date -Iseconds) $VERSION" >> deployments.log
REMOTE

# 3. 确认网关后面跑的是刚部署的镜像：版本号来自部署标签，git_sha 来自镜像构建参数
for svc in common m1 m2 m3; do
  if ! info="$(curl -fsS --max-time 10 "$gateway_url/ops/$svc/version")"; then
    echo "::error::无法经网关获取 ${svc} 的版本信息（${gateway_url}/ops/${svc}/version）"
    exit 1
  fi
  read -r running sha < <(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["version"], d["git_sha"])' <<< "$info")
  if [[ "$running" != "$VERSION" || "$sha" != "$EXPECTED_SHA" ]]; then
    echo "::error::${svc} 运行 ${running}（${sha}），期望 ${VERSION}（${EXPECTED_SHA}）"
    exit 1
  fi
done

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "gateway_url=$gateway_url" >> "$GITHUB_OUTPUT"
fi
echo "已部署 ${VERSION} 到 ${ENV_NAME}（${gateway_url}）"
