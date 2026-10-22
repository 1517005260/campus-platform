#!/usr/bin/env bash
# Shell 脚本检查（CI lint 任务执行）：
# 1. bash -n 语法检查；
# 2. 变量名后紧跟非 ASCII 字符（例如变量 file 后直接接全角括号）时必须写成 ${file}：部分 locale 下 bash 会把
#    多字节字符的首字节当作变量名的一部分，导致"未绑定的变量"。
set -euo pipefail
cd "$(dirname "$0")/.."

files=(scripts/*.sh deploy/*.sh deploy/postgres/*.sh deploy/docker/*.sh)
status=0
for f in "${files[@]}"; do
  bash -n "$f" || status=1
done
if LC_ALL=C grep -nE '\$[A-Za-z_][A-Za-z0-9_]*[^ -~]' "${files[@]}"; then
  echo "::error::以上变量后紧跟非 ASCII 字符，请写成 \${变量名}"
  status=1
fi
exit $status
