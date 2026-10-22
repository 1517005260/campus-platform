#!/usr/bin/env bash
# 从代码重新生成全部契约快照。改了接口或消息模型后运行，并把 contracts/ 的变化一起提交。
set -euo pipefail
cd "$(dirname "$0")/.."

for svc in common m1-seat m2-room m3-repair; do
  (cd "services/$svc" && uv run --no-sync python ../../scripts/export_openapi.py) > "contracts/openapi/$svc.json"
done
uv run --no-sync python scripts/export_event_schemas.py > contracts/events/schemas.json
echo "契约已更新：git diff contracts/"
