#!/usr/bin/env bash
# 给已有镜像追加标签，不重新构建。源标签不存在时失败。
#   测试环境集成测试通过后：scripts/retag_images.sh <提交号> verified-<提交号>
#   生产发布：            scripts/retag_images.sh verified-<提交号> v1.2.0
# 目标标签已存在时：指向同一镜像则跳过（重跑幂等），指向其他镜像则失败——版本标签一经发布不可改指。
set -euo pipefail
: "${REGISTRY:?需要 REGISTRY}"
SRC="$1"
DST="$2"

digest() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest}}' 2> /dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["digest"])'
}

for name in common m1-seat m2-room m3-repair frontend; do
  src="$REGISTRY/campus-$name:$SRC"
  dst="$REGISTRY/campus-$name:$DST"
  src_digest="$(digest "$src")" || { echo "::error::源镜像不存在：$src"; exit 1; }
  if dst_digest="$(digest "$dst")"; then
    if [[ "$dst_digest" == "$src_digest" ]]; then
      echo "已存在且一致，跳过：$dst"
      continue
    fi
    echo "::error::$dst 已指向其他镜像（${dst_digest}），拒绝改指"
    exit 1
  fi
  docker buildx imagetools create -t "$dst" "$src"
done
