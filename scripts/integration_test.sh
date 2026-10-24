#!/usr/bin/env bash
# 对已部署的环境跑跨模块集成测试。
# 用法：scripts/integration_test.sh <网关地址，如 http://test.example.com:8000> [期望版本]
# 环境变量 DEMO_PASSWORD：演示账号密码；未设置时依次取 .env、.env.example 中的值（与部署一致）
# 依赖取自 uv.lock 的 integration 组，在独立环境中运行，不改动本地 .venv
set -euo pipefail
cd "$(dirname "$0")/.."
export BASE_URL="$1"
export EXPECTED_VERSION="${2:-}"
if [[ -z "${DEMO_PASSWORD:-}" ]]; then
  DEMO_PASSWORD="$( (grep -hE '^DEMO_PASSWORD=.+' .env 2> /dev/null || true; grep -hE '^DEMO_PASSWORD=' .env.example) \
    | head -n 1 | cut -d= -f2- | tr -d "\"'")"
fi
export DEMO_PASSWORD
requirements="$(mktemp)"
trap 'rm -f "$requirements"' EXIT
uv export --frozen --only-group integration --no-hashes --no-emit-project > "$requirements"
uv run --isolated --no-project --with-requirements "$requirements" pytest tests/integration -v
