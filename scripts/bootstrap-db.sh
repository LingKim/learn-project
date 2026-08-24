#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
env_file="${project_root}/.env"

if [[ ! -f "${env_file}" ]]; then
  echo "缺少 .env，请先执行 make init-env。" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${env_file}"
set +a

: "${POSTGRES_CONTAINER_NAME:?缺少 POSTGRES_CONTAINER_NAME}"
: "${POSTGRES_ADMIN_USER:?缺少 POSTGRES_ADMIN_USER}"
: "${APP_DB_NAME:?缺少 APP_DB_NAME}"
: "${APP_DB_USER:?缺少 APP_DB_USER}"
: "${APP_DB_PASSWORD:?缺少 APP_DB_PASSWORD}"

if [[ "$(docker inspect --format '{{.State.Running}}' "${POSTGRES_CONTAINER_NAME}" 2>/dev/null)" != "true" ]]; then
  echo "PostgreSQL 容器 ${POSTGRES_CONTAINER_NAME} 未运行。" >&2
  exit 1
fi

docker exec -i "${POSTGRES_CONTAINER_NAME}" \
  psql \
  --username "${POSTGRES_ADMIN_USER}" \
  --dbname postgres \
  --set ON_ERROR_STOP=1 \
  --set app_db="${APP_DB_NAME}" \
  --set app_user="${APP_DB_USER}" \
  --set app_password="${APP_DB_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec

SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'app_db') \gexec

SELECT format('GRANT ALL PRIVILEGES ON DATABASE %I TO %I', :'app_db', :'app_user') \gexec
SQL

echo "数据库 ${APP_DB_NAME} 与用户 ${APP_DB_USER} 已就绪。"

