#!/usr/bin/env bash
# 可选：为某个 GitHub 环境生成随机密钥，写入该环境的 secrets，替换 .env.example 中的默认值。
# 生成范围：.env.example 中有默认值的密码，以及 @random-if-empty 标记的签名与服务间认证密钥；
# 默认留空的外部服务密钥（如 SMTP_PASSWORD）不生成。只生成尚不存在的项，可重复执行。
# 数据库与 RabbitMQ 密码在该环境首次部署时固定，应在首次部署前运行。
# 用法：scripts/gen_secrets.sh <test|production>
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_NAME="$1"
random_if_empty=" $(sed -n 's/^# @random-if-empty: *//p' .env.example) "
existing="$(gh secret list --env "$ENV_NAME" --json name --jq '.[].name')"
while IFS= read -r line; do
  key="${line%%=*}"
  [[ -z "$key" || "$key" == \#* ]] && continue
  if [[ -z "${line#*=}" && "$random_if_empty" != *" $key "* ]]; then
    continue # 外部服务密钥，由对应服务提供
  fi
  if grep -qx "$key" <<< "$existing"; then
    echo "已存在 ${ENV_NAME}/${key}，跳过"
    continue
  fi
  openssl rand -hex 24 | gh secret set "$key" --env "$ENV_NAME"
  echo "已设置 ${ENV_NAME}/${key}"
done < .env.example
