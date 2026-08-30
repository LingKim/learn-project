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
: "${DATABASE_URL:?缺少 DATABASE_URL}"

if [[ ! "${APP_DB_NAME}" =~ ^[a-zA-Z0-9_]+$ ]] || [[ ! "${APP_DB_USER}" =~ ^[a-zA-Z0-9_]+$ ]]; then
  echo "数据库名或用户名包含不支持的字符。" >&2
  exit 1
fi

e2e_db_name="${APP_DB_NAME}_e2e"
run_id="$(date +%s)-${RANDOM}"
export DATABASE_URL="${DATABASE_URL%/*}/${e2e_db_name}"
export ENVIRONMENT="test"
export AUTH_ALLOWED_ORIGINS="http://127.0.0.1:3100"
export AUTH_REDIS_KEY_PREFIX="${AUTH_REDIS_KEY_PREFIX:-xuemian:test:auth}:e2e:${run_id}"
export RUSTFS_QUARANTINE_BUCKET="xuemian-e2e-quarantine-${run_id}"
export RUSTFS_DOCUMENTS_BUCKET="xuemian-e2e-documents-${run_id}"
export RUSTFS_RECORDINGS_BUCKET="xuemian-e2e-recordings-${run_id}"
export RUSTFS_TEMPORARY_BUCKET="xuemian-e2e-temporary-${run_id}"
export PROFILE_SMOKE_PASSWORD="ProfileSmoke9!${RANDOM}"
export PROFILE_SMOKE_PYTHON="${project_root}/backend/.venv/bin/python"

docker exec -i "${POSTGRES_CONTAINER_NAME}" \
  psql \
  --username "${POSTGRES_ADMIN_USER}" \
  --dbname postgres \
  --set ON_ERROR_STOP=1 \
  --set e2e_db="${e2e_db_name}" \
  --set app_user="${APP_DB_USER}" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'e2e_db', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'e2e_db') \gexec
SQL

api_pid=""
worker_pid=""
cleanup() {
  if [[ -n "${api_pid}" ]]; then
    kill "${api_pid}" 2>/dev/null || true
    wait "${api_pid}" 2>/dev/null || true
  fi
  if [[ -n "${worker_pid}" ]]; then
    kill "${worker_pid}" 2>/dev/null || true
    wait "${worker_pid}" 2>/dev/null || true
  fi
  (
    cd "${project_root}/backend"
    .venv/bin/python scripts/cleanup_file_e2e.py
    .venv/bin/python scripts/cleanup_auth_e2e.py
  ) || echo "警告：个人资料 E2E 临时数据清理失败，请人工复核 ${e2e_db_name}。" >&2
}
trap cleanup EXIT

(
  cd "${project_root}/backend"
  .venv/bin/alembic upgrade head
  .venv/bin/python scripts/cleanup_file_e2e.py
  .venv/bin/python scripts/cleanup_auth_e2e.py
  .venv/bin/xuemian-ai-init-storage
)

(
  cd "${project_root}/backend"
  exec .venv/bin/uvicorn xuemian_ai.main:app --host 127.0.0.1 --port 8011 --no-access-log
) &
api_pid=$!

(
  cd "${project_root}/backend"
  exec .venv/bin/xuemian-ai-file-worker
) &
worker_pid=$!

for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl --max-time 2 --silent --fail http://127.0.0.1:8011/api/v1/health/live >/dev/null; then
    break
  fi
  sleep 0.5
done
curl --max-time 2 --silent --fail http://127.0.0.1:8011/api/v1/health/live >/dev/null

"${project_root}/scripts/curl-profile-smoke.sh"
