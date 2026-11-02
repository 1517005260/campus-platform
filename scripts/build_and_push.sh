#!/usr/bin/env bash
# 构建并推送镜像。标签用 git 提交号，测试和生产部署同一个镜像；不推送 latest。
# 构建缓存存放在镜像仓库的 <镜像>:buildcache 标签中。
# 用法：scripts/build_and_push.sh <tag> [服务...]     服务取 common m1-seat m2-room m3-repair frontend，省略时全部构建
# 需要环境变量 REGISTRY（如 ghcr.io/org/campus-platform）和 docker buildx
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="$1"
shift
: "${REGISTRY:?需要 REGISTRY}"
SHA="$(git rev-parse HEAD)"
SERVICES=("$@")
[[ ${#SERVICES[@]} -gt 0 ]] || SERVICES=(common m1-seat m2-room m3-repair frontend)

for svc in "${SERVICES[@]}"; do
  case "$svc" in
    frontend) context=frontend file=frontend/Dockerfile ;;
    common | m1-seat | m2-room | m3-repair) context=. file="services/$svc/Dockerfile" ;;
    *) echo "未知服务：$svc" >&2; exit 1 ;;
  esac
  image="$REGISTRY/campus-$svc"
  docker buildx build "$context" -f "$file" \
    --build-arg APP_VERSION="$TAG" --build-arg GIT_SHA="$SHA" \
    --label org.opencontainers.image.revision="$SHA" \
    --cache-from "type=registry,ref=$image:buildcache" \
    --cache-to "type=registry,ref=$image:buildcache,mode=max" \
    -t "$image:$TAG" --push
done
