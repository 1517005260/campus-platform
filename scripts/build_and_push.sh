#!/usr/bin/env bash
# 构建并推送全部镜像。标签用 git 提交号，测试和生产部署同一个镜像。
# 构建缓存存放在镜像仓库的 <镜像>:buildcache 标签中；不推送 latest，部署一律按提交号或版本号引用镜像。
# 用法：scripts/build_and_push.sh <tag>        需要环境变量 REGISTRY（如 ghcr.io/org/campus-platform）和 docker buildx
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="$1"
: "${REGISTRY:?需要 REGISTRY}"
SHA="$(git rev-parse HEAD)"

build() { # build <镜像名> <上下文> [Dockerfile]
  local image="$REGISTRY/campus-$1" context="$2" file="${3:-$2/Dockerfile}"
  docker buildx build "$context" -f "$file" \
    --build-arg APP_VERSION="$TAG" --build-arg GIT_SHA="$SHA" \
    --label org.opencontainers.image.revision="$SHA" \
    --cache-from "type=registry,ref=$image:buildcache" \
    --cache-to "type=registry,ref=$image:buildcache,mode=max" \
    -t "$image:$TAG" --push
}

for svc in common m1-seat m2-room m3-repair; do
  build "$svc" . "services/$svc/Dockerfile"
done
build frontend frontend
