#!/bin/bash
# 开发环境专用：创建测试库 ${POSTGRES_DB}_test（结构与角色同开发库），测试只连这个库，不会清空开发数据。
# 由 docker-compose.dev.yml 挂载到 /docker-entrypoint-initdb.d/，在 init.sh 之后执行（按文件名排序）；
# 也可随时用 `make test-db` 执行（可重复执行）。测试/生产环境不挂载此脚本。
set -euo pipefail

TEST_DB="${POSTGRES_DB}_test"

exists=$(psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '${TEST_DB}'")
if [ "$exists" != "1" ]; then
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE ${TEST_DB} OWNER ${POSTGRES_USER}"
fi

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$TEST_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS btree_gist;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS common AUTHORIZATION common_svc;
CREATE SCHEMA IF NOT EXISTS m1 AUTHORIZATION m1_seat;
CREATE SCHEMA IF NOT EXISTS m2 AUTHORIZATION m2_room;
CREATE SCHEMA IF NOT EXISTS m3 AUTHORIZATION m3_repair;
GRANT CONNECT ON DATABASE ${TEST_DB} TO common_svc, m1_seat, m2_room, m3_repair;
SQL
echo "测试库 ${TEST_DB} 已就绪"
