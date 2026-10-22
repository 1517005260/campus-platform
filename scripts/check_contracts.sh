#!/usr/bin/env bash
# CI 契约检查。
# 1. 漂移：从代码导出的契约必须与 contracts/ 下提交的快照一致，否则说明改了接口却没更新契约。
#    前端类型与契约的一致性由 CI 的 frontend 任务检查（npm run gen:types 后比对）。
# 2. 破坏性变更：与目标分支的快照对比（oasdiff）。有破坏性变更时，PR 必须带
#    breaking-change-approved 标签（约定：所有调用方确认已适配后才打）。
#
# 环境变量：BASE_REF（目标分支，默认 main）、PR_LABELS（逗号分隔的 PR 标签）、
#           CHECK_BREAKING（默认 true；为 false 时只检查漂移）
set -euo pipefail
cd "$(dirname "$0")/.."

BASE_REF="${BASE_REF:-main}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
status=0

echo "== 检查契约漂移"
for svc in common m1-seat m2-room m3-repair; do
  (cd "services/$svc" && uv run --no-sync python ../../scripts/export_openapi.py) > "$tmp/$svc.json"
  if ! diff -q "$tmp/$svc.json" "contracts/openapi/$svc.json" > /dev/null; then
    echo "::error::$svc 的接口与 contracts/openapi/$svc.json 不一致。运行 scripts/update_contracts.sh 并提交。"
    diff -u "contracts/openapi/$svc.json" "$tmp/$svc.json" | head -40 || true
    status=1
  fi
done
uv run --no-sync python scripts/export_event_schemas.py > "$tmp/events.json"
if ! diff -q "$tmp/events.json" contracts/events/schemas.json > /dev/null; then
  echo "::error::消息模型与 contracts/events/schemas.json 不一致。运行 scripts/update_contracts.sh 并提交。"
  status=1
fi

echo "== 检查破坏性变更（对比 origin/${BASE_REF}）"
if [[ "${CHECK_BREAKING:-true}" != "true" ]]; then
  echo "非 PR 构建，跳过破坏性变更检查"
elif git rev-parse --verify --quiet "origin/$BASE_REF" > /dev/null; then
  breaking=0
  for svc in common m1-seat m2-room m3-repair; do
    base="$tmp/base-$svc.json"
    git show "origin/$BASE_REF:contracts/openapi/$svc.json" > "$base" 2> /dev/null || continue
    if ! docker run --rm -v "$tmp:/base:ro" -v "$PWD/contracts/openapi:/head:ro" "${OASDIFF_IMAGE:-tufin/oasdiff:v1.11.7}" \
        breaking "/base/base-$svc.json" "/head/$svc.json" --fail-on ERR; then
      echo "::warning::$svc 存在破坏性接口变更"
      breaking=1
    fi
  done
  if [[ $breaking == 1 && ",${PR_LABELS:-}," != *",breaking-change-approved,"* ]]; then
    echo "::error::存在破坏性接口变更。请调用方确认适配后，给 PR 加上 breaking-change-approved 标签。"
    status=1
  fi
else
  echo "未找到 origin/${BASE_REF}，跳过破坏性变更检查"
fi

exit $status
