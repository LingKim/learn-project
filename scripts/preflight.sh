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
REDIS_CONTAINER_NAME="${REDIS_CONTAINER_NAME:-myRedis}"

if [[ "$(docker inspect --format '{{.State.Running}}' "${POSTGRES_CONTAINER_NAME}" 2>/dev/null)" != "true" ]]; then
  echo "PostgreSQL 容器 ${POSTGRES_CONTAINER_NAME} 未运行。" >&2
  exit 1
fi

if [[ "$(docker inspect --format '{{.State.Running}}' "${REDIS_CONTAINER_NAME}" 2>/dev/null)" != "true" ]]; then
  echo "Redis 容器 ${REDIS_CONTAINER_NAME} 未运行。" >&2
  exit 1
fi

docker exec "${POSTGRES_CONTAINER_NAME}" \
  pg_isready --username "${POSTGRES_ADMIN_USER}" --dbname postgres >/dev/null

if [[ "$(docker exec "${REDIS_CONTAINER_NAME}" redis-cli ping)" != "PONG" ]]; then
  echo "Redis 容器 ${REDIS_CONTAINER_NAME} 未返回 PONG。" >&2
  exit 1
fi

echo "PostgreSQL 与 Redis 已就绪。"
