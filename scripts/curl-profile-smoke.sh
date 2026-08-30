#!/usr/bin/env bash
set -euo pipefail

: "${PROFILE_SMOKE_PASSWORD:?请通过 PROFILE_SMOKE_PASSWORD 提供临时测试密码}"

base_url="${PROFILE_SMOKE_BASE_URL:-http://127.0.0.1:8011/api/v1}"
run_id="$(date +%s)-${RANDOM}"
username="profile_${run_id//-/_}"
work_dir="$(mktemp -d)"
response_file="${work_dir}/response.json"
avatar_source="${work_dir}/source.png"
avatar_result="${work_dir}/avatar.webp"

cleanup() {
  rm -rf "${work_dir}"
}
trap cleanup EXIT

request() {
  local expected_status="$1"
  shift
  local actual_status
  actual_status="$(curl --max-time 10 --silent --show-error --output "${response_file}" --write-out '%{http_code}' "$@")"
  if [[ "${actual_status}" != "${expected_status}" ]]; then
    echo "个人资料 smoke 失败：期望 HTTP ${expected_status}，实际 ${actual_status}。" >&2
    jq '{code, error_key, message}' "${response_file}" >&2 || true
    exit 1
  fi
}

assert_error_key() {
  local expected="$1"
  local actual
  actual="$(jq -r '.error_key // empty' "${response_file}")"
  test "${actual}" = "${expected}"
}

register_body="$(jq -nc \
  --arg username "${username}" \
  --arg password "${PROFILE_SMOKE_PASSWORD}" \
  '{username: $username, nickname: "资料测试用户", password: $password}')"
request 201 \
  --header 'Content-Type: application/json' \
  --data "${register_body}" \
  "${base_url}/auth/register"
access_token="$(jq -r '.data.access_token' "${response_file}")"
test -n "${access_token}"

request 401 "${base_url}/users/me/profile"
assert_error_key AUTH_ACCESS_TOKEN_INVALID

request 200 \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/users/me/profile"
test "$(jq -r '.data.version' "${response_file}")" = "0"
test "$(jq -r '.data.active_weaknesses | length' "${response_file}")" = "0"

profile_body="$(jq -nc '{
  version: 0,
  nickname: "更新后的昵称",
  target_job: "  后端工程师  ",
  experience_months: 30,
  target_level: "senior",
  target_skills: ["Python", " python ", "FastAPI"],
  focus_topics: ["SQLAlchemy"],
  learning_goal: "完善工程化能力",
  preferred_language: "zh-CN"
}')"
request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --request PATCH \
  --data "${profile_body}" \
  "${base_url}/users/me/profile"
test "$(jq -r '.data.version' "${response_file}")" = "1"
test "$(jq -r '.data.experience_display' "${response_file}")" = "2 年 6 个月"
test "$(jq -r '.data.target_skills | length' "${response_file}")" = "2"

request 409 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --request PATCH \
  --data '{"version":0,"target_job":"陈旧覆盖"}' \
  "${base_url}/users/me/profile"
assert_error_key PROFILE_VERSION_CONFLICT

python_executable="${PROFILE_SMOKE_PYTHON:-python3}"
"${python_executable}" -c 'from PIL import Image; import sys; Image.new("RGB", (900, 500), (220, 170, 80)).save(sys.argv[1], "PNG")' "${avatar_source}"
avatar_size="$(wc -c < "${avatar_source}" | tr -d ' ')"
avatar_body="$(jq -nc --argjson size "${avatar_size}" '{
  filename: "avatar.png",
  size: $size,
  declared_mime: "image/png",
  profile_version: 1
}')"
request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --header "Idempotency-Key: avatar-${run_id}" \
  --data "${avatar_body}" \
  "${base_url}/users/me/avatar-upload-sessions"
upload_id="$(jq -r '.data.id' "${response_file}")"
upload_url="$(jq -r '.data.upload_url' "${response_file}")"

upload_status="$(curl --max-time 10 --silent --show-error --output /dev/null --write-out '%{http_code}' \
  --header 'Content-Type: image/png' --upload-file "${avatar_source}" "${upload_url}")"
test "${upload_status}" = "200"

request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --request POST \
  "${base_url}/users/me/avatar-upload-sessions/${upload_id}/complete"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  sleep 0.5
  request 200 \
    --header "Authorization: Bearer ${access_token}" \
    --request POST \
    "${base_url}/users/me/avatar-upload-sessions/${upload_id}/complete"
  avatar_status="$(jq -r '.data.status' "${response_file}")"
  if [[ "${avatar_status}" = "completed" ]]; then
    break
  fi
  if [[ "${avatar_status}" = "failed" ]]; then
    jq '{data}' "${response_file}" >&2
    exit 1
  fi
done
test "${avatar_status}" = "completed"

avatar_http="$(curl --max-time 10 --silent --show-error --output "${avatar_result}" --write-out '%{http_code}' \
  --header "Authorization: Bearer ${access_token}" "${base_url}/users/me/avatar")"
test "${avatar_http}" = "200"
"${python_executable}" -c 'from PIL import Image; import sys; image=Image.open(sys.argv[1]); assert image.format == "WEBP" and image.size == (512, 512) and not image.getexif()' "${avatar_result}"

request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --request DELETE \
  --data '{"version":2}' \
  "${base_url}/users/me/avatar"
test "$(jq -r '.data.version' "${response_file}")" = "3"
test "$(jq -r '.data.avatar_set' "${response_file}")" = "false"

request 404 \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/users/me/avatar"
assert_error_key AVATAR_NOT_SET

echo "个人资料与头像 curl smoke 全部通过。"
