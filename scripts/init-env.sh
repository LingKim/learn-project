#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${script_dir}/.." && pwd)"
target_file="${project_root}/.env"
template_file="${project_root}/.env.example"

command -v openssl >/dev/null 2>&1 || {
  echo "缺少 openssl，无法安全生成本地凭据。" >&2
  exit 1
}

app_db_password="$(openssl rand -hex 24)"
rustfs_access_key="$(openssl rand -hex 12)"
rustfs_secret_key="$(openssl rand -hex 32)"
auth_access_secret="$(openssl rand -hex 32)"
auth_refresh_secret="$(openssl rand -hex 32)"
auth_refresh_digest_secret="$(openssl rand -hex 32)"
auth_fingerprint_secret="$(openssl rand -hex 32)"

if [[ -f "${target_file}" ]]; then
  append_secret_if_missing() {
    local key="$1"
    local value="$2"
    if ! grep -q "^${key}=" "${target_file}"; then
      printf '%s=%s\n' "${key}" "${value}" >> "${target_file}"
    fi
  }

  append_value_if_missing() {
    local key="$1"
    local value="$2"
    if ! grep -q "^${key}=" "${target_file}"; then
      printf '%s=%s\n' "${key}" "${value}" >> "${target_file}"
    fi
  }

  umask 077
  append_secret_if_missing AUTH_ACCESS_SECRET "${auth_access_secret}"
  append_secret_if_missing AUTH_REFRESH_SECRET "${auth_refresh_secret}"
  append_secret_if_missing AUTH_REFRESH_DIGEST_SECRET "${auth_refresh_digest_secret}"
  append_secret_if_missing AUTH_FINGERPRINT_SECRET "${auth_fingerprint_secret}"
  append_value_if_missing AUTH_ISSUER xuemian-ai
  append_value_if_missing AUTH_AUDIENCE xuemian-ai-web
  append_value_if_missing AUTH_ACCESS_MINUTES 15
  append_value_if_missing AUTH_REFRESH_DAYS 7
  append_value_if_missing AUTH_COOKIE_SECURE false
  append_value_if_missing AUTH_ALLOWED_ORIGINS http://localhost:3000
  append_value_if_missing AUTH_REDIS_KEY_PREFIX xuemian:development:auth
  echo "已为现有 .env 补齐缺失的认证配置；秘密值未输出。"
  exit 0
fi

umask 077
awk \
  -v db_password="${app_db_password}" \
  -v rustfs_access="${rustfs_access_key}" \
  -v rustfs_secret="${rustfs_secret_key}" \
  -v auth_access="${auth_access_secret}" \
  -v auth_refresh="${auth_refresh_secret}" \
  -v auth_digest="${auth_refresh_digest_secret}" \
  -v auth_fingerprint="${auth_fingerprint_secret}" '
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
  /^AUTH_ACCESS_SECRET=/ {
    print "AUTH_ACCESS_SECRET=" auth_access
    next
  }
  /^AUTH_REFRESH_SECRET=/ {
    print "AUTH_REFRESH_SECRET=" auth_refresh
    next
  }
  /^AUTH_REFRESH_DIGEST_SECRET=/ {
    print "AUTH_REFRESH_DIGEST_SECRET=" auth_digest
    next
  }
  /^AUTH_FINGERPRINT_SECRET=/ {
    print "AUTH_FINGERPRINT_SECRET=" auth_fingerprint
    next
  }
  { print }
' "${template_file}" > "${target_file}"

echo "已生成本地 .env；秘密值未输出。"
