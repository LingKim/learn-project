#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
target_file="${project_root}/.env"
template_file="${project_root}/.env.example"

if [[ -f "${target_file}" ]]; then
  echo ".env 已存在，未覆盖。"
  exit 0
fi

command -v openssl >/dev/null 2>&1 || {
  echo "缺少 openssl，无法安全生成本地凭据。" >&2
  exit 1
}

app_db_password="$(openssl rand -hex 24)"
rustfs_access_key="$(openssl rand -hex 12)"
rustfs_secret_key="$(openssl rand -hex 32)"

umask 077
awk \
  -v db_password="${app_db_password}" \
  -v rustfs_access="${rustfs_access_key}" \
  -v rustfs_secret="${rustfs_secret_key}" '
  /^APP_DB_PASSWORD=/ {
    print "APP_DB_PASSWORD=" db_password
    next
  }
  /^DATABASE_URL=/ {
    print "DATABASE_URL=postgresql+asyncpg://xuemian_ai_app:" db_password "@localhost:5432/xuemian_ai"
    next
  }
  /^RUSTFS_ACCESS_KEY=/ {
    print "RUSTFS_ACCESS_KEY=" rustfs_access
    next
  }
  /^RUSTFS_SECRET_KEY=/ {
    print "RUSTFS_SECRET_KEY=" rustfs_secret
    next
  }
  { print }
' "${template_file}" > "${target_file}"

echo "已生成本地 .env；秘密值未输出。"

