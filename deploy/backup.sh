#!/usr/bin/env bash
# 数据库备份：在部署目录（/opt/campus/<环境>）中执行，pg_dump 自定义格式写入 backups/。
# 按类型分别保留：部署前备份（pre-deploy-*）与其他备份（daily 等）各保留最近 KEEP 份，频繁部署不会挤掉每日备份。
# 备份只在本机；需要异地保存时把 backups/ 同步到其他位置。
#   ./backup.sh [标签]        部署前由 deploy.sh 调用（标签为 pre-deploy-<版本>）；每日由 cron 调用（标签 daily）
# 恢复：docker compose -p campus-<环境> exec -T postgres pg_restore -U campus -d campus --clean --if-exists < backups/<文件>
set -euo pipefail
cd "$(dirname "$0")"

LABEL="${1:-manual}"
KEEP="${BACKUP_KEEP:-14}"
PROJECT="campus-$(basename "$PWD")"

if [[ -z "$(docker compose -p "$PROJECT" ps -q postgres 2> /dev/null)" ]]; then
  echo "postgres 未运行，跳过备份"
  exit 0
fi

umask 077
mkdir -p backups
file="backups/campus-$(date +%Y%m%d-%H%M%S)-${LABEL//[^A-Za-z0-9._-]/_}.dump"
docker compose -p "$PROJECT" exec -T postgres pg_dump -U campus -d campus -Fc > "$file.tmp"
mv "$file.tmp" "$file"
echo "已备份到 ${file}（$(du -h "$file" | cut -f1)）"

# 每类只保留最近 KEEP 份
kind="other"
[[ "$LABEL" == pre-deploy-* ]] && kind="pre-deploy"
count=0
while IFS= read -r f; do
  case "$f" in
    *-pre-deploy-*) [[ "$kind" == "pre-deploy" ]] || continue ;;
    *) [[ "$kind" == "other" ]] || continue ;;
  esac
  count=$((count + 1))
  if ((count > KEEP)); then rm -- "$f"; fi
done < <(ls -1t backups/*.dump 2> /dev/null || true)
