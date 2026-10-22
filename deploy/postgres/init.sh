#!/bin/bash
# Postgres 首次初始化时执行（挂载到 /docker-entrypoint-initdb.d/）。
# 每个服务一个数据库角色，只拥有自己的 schema，从权限上保证"不直接访问其他模块的数据库"。
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE EXTENSION IF NOT EXISTS btree_gist;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL

create_service_role() {
  local role=$1 schema=$2 password=$3
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE ${role} LOGIN PASSWORD '${password}';
CREATE SCHEMA ${schema} AUTHORIZATION ${role};
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${role};
SQL
}

create_service_role common_svc common "${DB_PASSWORD_COMMON}"
create_service_role m1_seat m1 "${DB_PASSWORD_M1}"
create_service_role m2_room m2 "${DB_PASSWORD_M2}"
create_service_role m3_repair m3 "${DB_PASSWORD_M3}"
