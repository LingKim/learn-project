#!/usr/bin/env bash
set -euo pipefail

: "${AUTH_SMOKE_PASSWORD:?请通过 AUTH_SMOKE_PASSWORD 提供临时测试密码}"

base_url="${AUTH_SMOKE_BASE_URL:-http://127.0.0.1:8000/api/v1}"
origin="${AUTH_SMOKE_ORIGIN:-http://localhost:3000}"
run_id="$(date +%s)-${RANDOM}"
username="smoke_${run_id//-/_}"
rate_username="rate_${run_id//-/_}"
nickname="认证测试用户"
work_dir="$(mktemp -d)"
response_file="${work_dir}/response.json"
cookie_jar="${work_dir}/cookies.txt"
old_cookie_jar="${work_dir}/old-cookies.txt"

cleanup() {
  rm -rf "${work_dir}"
}
trap cleanup EXIT

request() {
  local expected_status="$1"
  shift
  local actual_status
  actual_status="$(curl --silent --show-error --output "${response_file}" --write-out '%{http_code}' "$@")"
  if [[ "${actual_status}" != "${expected_status}" ]]; then
    echo "认证 smoke 失败：期望 HTTP ${expected_status}，实际 ${actual_status}。" >&2
    jq '{code, error_key, message}' "${response_file}" >&2 || true
    exit 1
  fi
}

assert_error_key() {
  local expected="$1"
  local actual
  actual="$(jq -r '.error_key // empty' "${response_file}")"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "认证 smoke 失败：期望 error_key=${expected}，实际 ${actual:-<empty>}。" >&2
    exit 1
  fi
}

extract_access_token() {
  jq -r '.data.access_token // empty' "${response_file}"
}

register_body="$(jq -nc \
  --arg username "${username}" \
  --arg nickname "${nickname}" \
  --arg password "${AUTH_SMOKE_PASSWORD}" \
  '{username: $username, nickname: $nickname, password: $password}')"

request 201 \
  --cookie-jar "${cookie_jar}" \
  --header 'Content-Type: application/json' \
  --header "Origin: ${origin}" \
  --data "${register_body}" \
  "${base_url}/auth/register"
access_token="$(extract_access_token)"
test -n "${access_token}"
echo "PASS register 201"

request 409 \
  --header 'Content-Type: application/json' \
  --header "Origin: ${origin}" \
  --data "${register_body}" \
  "${base_url}/auth/register"
assert_error_key AUTH_USERNAME_TAKEN
echo "PASS duplicate username 409"

request 200 \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/auth/me"
echo "PASS me 200"

request 401 "${base_url}/auth/me"
assert_error_key AUTH_ACCESS_TOKEN_INVALID
echo "PASS unauthenticated me 401"

cp "${cookie_jar}" "${old_cookie_jar}"
request 200 \
  --cookie "${cookie_jar}" \
  --cookie-jar "${cookie_jar}" \
  --header "Origin: ${origin}" \
  --request POST \
  "${base_url}/auth/refresh"
rotated_access_token="$(extract_access_token)"
test -n "${rotated_access_token}"
echo "PASS refresh rotation 200"

request 401 \
  --cookie "${old_cookie_jar}" \
  --header "Origin: ${origin}" \
  --request POST \
  "${base_url}/auth/refresh"
assert_error_key AUTH_REFRESH_TOKEN_INVALID
echo "PASS old refresh replay 401"

request 401 \
  --cookie "${cookie_jar}" \
  --header "Origin: ${origin}" \
  --request POST \
  "${base_url}/auth/refresh"
echo "PASS replay revoked family 401"

login_body="$(jq -nc \
  --arg username "${username}" \
  --arg password "${AUTH_SMOKE_PASSWORD}" \
  '{username: $username, password: $password}')"
request 200 \
  --cookie-jar "${cookie_jar}" \
  --header 'Content-Type: application/json' \
  --data "${login_body}" \
  "${base_url}/auth/login"
access_token="$(extract_access_token)"
test -n "${access_token}"
echo "PASS login 200"

wrong_login_body="$(jq -nc \
  --arg username "${username}" \
  '{username: $username, password: "definitely-wrong"}')"
request 401 \
  --header 'Content-Type: application/json' \
  --data "${wrong_login_body}" \
  "${base_url}/auth/login"
assert_error_key AUTH_INVALID_CREDENTIALS
echo "PASS invalid credentials 401"

request 200 \
  --cookie "${cookie_jar}" \
  --header "Authorization: Bearer ${access_token}" \
  --header "Origin: ${origin}" \
  --request POST \
  "${base_url}/auth/logout"
echo "PASS logout 200"

request 401 \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/auth/me"
assert_error_key AUTH_SESSION_REVOKED
echo "PASS revoked access token 401"

rate_register_body="$(jq -nc \
  --arg username "${rate_username}" \
  --arg nickname "${nickname}" \
  --arg password "${AUTH_SMOKE_PASSWORD}" \
  '{username: $username, nickname: $nickname, password: $password}')"
request 201 \
  --cookie-jar "${cookie_jar}" \
  --header 'Content-Type: application/json' \
  --data "${rate_register_body}" \
  "${base_url}/auth/register"

rate_login_body="$(jq -nc \
  --arg username "${rate_username}" \
  '{username: $username, password: "definitely-wrong"}')"
for _ in 1 2 3 4; do
  request 401 \
    --header 'Content-Type: application/json' \
    --data "${rate_login_body}" \
    "${base_url}/auth/login"
done
request 429 \
  --header 'Content-Type: application/json' \
  --data "${rate_login_body}" \
  "${base_url}/auth/login"
assert_error_key AUTH_RATE_LIMITED
echo "PASS account rate limit 429"

echo "认证 curl smoke 全部通过。临时凭据与 Cookie 文件已安排清理。"
