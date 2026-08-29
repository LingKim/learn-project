#!/usr/bin/env bash
set -euo pipefail

: "${FILE_SMOKE_PASSWORD:?请通过 FILE_SMOKE_PASSWORD 提供临时测试密码}"

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_url="${FILE_SMOKE_BASE_URL:-http://127.0.0.1:8000/api/v1}"
run_id="$(date +%s)-${RANDOM}"
username="file_smoke_${run_id//-/_}"
second_username="other_${run_id//-/_}"
work_dir="$(mktemp -d)"
response_file="${work_dir}/response.json"
access_token=""
default_knowledge_base_id=""
second_knowledge_base_id=""
last_file_id=""
last_sha256=""

cleanup() {
  if [[ -n "${access_token}" ]]; then
    (
      cd "${project_root}/backend"
      .venv/bin/python scripts/cleanup_file_smoke.py "${username}"
      .venv/bin/python scripts/cleanup_file_smoke.py "${second_username}"
    ) >/dev/null 2>&1 || true
  fi
  rm -rf "${work_dir}"
}
trap cleanup EXIT

request() {
  local expected_status="$1"
  shift
  local actual_status
  actual_status="$(curl --silent --show-error --output "${response_file}" --write-out '%{http_code}' "$@")"
  if [[ "${actual_status}" != "${expected_status}" ]]; then
    echo "文件 smoke 失败：期望 HTTP ${expected_status}，实际 ${actual_status}。" >&2
    jq '{code, error_key, message}' "${response_file}" >&2 || true
    exit 1
  fi
  local body_code
  body_code="$(jq -r '.code // empty' "${response_file}" 2>/dev/null || true)"
  if [[ -n "${body_code}" && "${body_code}" != "${actual_status}" ]]; then
    echo "文件 smoke 失败：HTTP ${actual_status} 与 body code ${body_code} 不一致。" >&2
    exit 1
  fi
}

assert_error_key() {
  local expected="$1"
  local actual
  actual="$(jq -r '.error_key // empty' "${response_file}")"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "文件 smoke 失败：期望 error_key=${expected}，实际 ${actual:-<empty>}。" >&2
    exit 1
  fi
}

sha256_file() {
  openssl dgst -sha256 "$1" | awk '{print $NF}'
}

md5_file() {
  openssl dgst -md5 "$1" | awk '{print $NF}'
}

create_fixtures() {
  printf 'interview notes\n' >"${work_dir}/notes.txt"
  printf '# Interview\n\nCandidate notes.\n' >"${work_dir}/notes.md"
  "${project_root}/backend/.venv/bin/python" - "${work_dir}" <<'PY'
import io
import os
import sys
import zipfile
from pathlib import Path

from pypdf import PdfWriter

root = Path(sys.argv[1])
writer = PdfWriter()
writer.add_blank_page(width=100, height=100)
with (root / "resume.pdf").open("wb") as output:
    writer.write(output)

xml = (
    b'<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>'
    b"Interview document"
    b"</w:t></w:r></w:p></w:body></w:document>"
)
with zipfile.ZipFile(root / "document.docx", "w", compression=zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("[Content_Types].xml", b"<Types />")
    archive.writestr("word/document.xml", xml)

with zipfile.ZipFile(root / "large.docx", "w", compression=zipfile.ZIP_STORED) as archive:
    archive.writestr("[Content_Types].xml", b"<Types />")
    archive.writestr("word/document.xml", xml)
    archive.writestr("word/media/padding.bin", os.urandom(21 * 1024 * 1024))
PY
}

put_single() {
  local upload_url="$1"
  local file_path="$2"
  local mime="$3"
  local status
  status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' \
    --request PUT --header "Content-Type: ${mime}" --data-binary "@${file_path}" "${upload_url}")"
  [[ "${status}" == "200" ]] || {
    echo "单文件 PUT 失败：HTTP ${status}" >&2
    exit 1
  }
}

put_multipart() {
  local session_id="$1"
  local first_url="$2"
  local file_path="$3"
  split -b 16777216 "${file_path}" "${work_dir}/part-"
  local second_body='{"part_numbers":[2]}'
  request 200 \
    --header "Authorization: Bearer ${access_token}" \
    --header 'Content-Type: application/json' \
    --data "${second_body}" \
    "${base_url}/file-upload-sessions/${session_id}/sign-parts"
  local second_url
  second_url="$(jq -r '.data[0].upload_url' "${response_file}")"
  local first_headers="${work_dir}/part-1.headers"
  local second_headers="${work_dir}/part-2.headers"
  curl --silent --show-error --dump-header "${first_headers}" --output /dev/null \
    --request PUT --data-binary "@${work_dir}/part-aa" "${first_url}"
  curl --silent --show-error --dump-header "${second_headers}" --output /dev/null \
    --request PUT --data-binary "@${work_dir}/part-ab" "${second_url}"
  local etag_one etag_two
  etag_one="$(awk 'BEGIN{IGNORECASE=1} /^etag:/{gsub(/\r|"/, "", $2); print $2}' "${first_headers}")"
  etag_two="$(awk 'BEGIN{IGNORECASE=1} /^etag:/{gsub(/\r|"/, "", $2); print $2}' "${second_headers}")"
  jq -nc --arg e1 "${etag_one}" --arg e2 "${etag_two}" \
    '{parts:[{part_number:1,etag:$e1},{part_number:2,etag:$e2}]}' >"${work_dir}/complete.json"
}

upload_file() {
  local knowledge_base_id="$1"
  local file_path="$2"
  local mime="$3"
  local size sha256 md5 body session_id replay_session_id upload_mode upload_url complete_body
  local idempotency_key
  size="$(wc -c <"${file_path}" | tr -d ' ')"
  sha256="$(sha256_file "${file_path}")"
  md5="$(md5_file "${file_path}")"
  body="$(jq -nc --arg filename "$(basename "${file_path}")" --arg mime "${mime}" \
    --arg sha256 "${sha256}" --arg md5 "${md5}" --argjson size "${size}" \
    '{filename:$filename,size:$size,declared_mime:$mime,client_sha256:$sha256,client_md5:$md5}')"
  idempotency_key="upload-${run_id}-$(basename "${file_path}")"
  request 200 \
    --header "Authorization: Bearer ${access_token}" \
    --header "Idempotency-Key: ${idempotency_key}" \
    --header 'Content-Type: application/json' \
    --data "${body}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}/file-upload-sessions"
  session_id="$(jq -r '.data.session_id' "${response_file}")"
  request 200 \
    --header "Authorization: Bearer ${access_token}" \
    --header "Idempotency-Key: ${idempotency_key}" \
    --header 'Content-Type: application/json' \
    --data "${body}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}/file-upload-sessions"
  replay_session_id="$(jq -r '.data.session_id' "${response_file}")"
  [[ "${replay_session_id}" == "${session_id}" ]]
  upload_mode="$(jq -r '.data.upload_mode' "${response_file}")"
  upload_url="$(jq -r '.data.upload_url // .data.parts[0].upload_url' "${response_file}")"
  complete_body='{"parts":[]}'
  if [[ "${upload_mode}" == "single" ]]; then
    put_single "${upload_url}" "${file_path}" "${mime}"
  else
    put_multipart "${session_id}" "${upload_url}" "${file_path}"
    complete_body="$(<"${work_dir}/complete.json")"
  fi
  request 200 \
    --header "Authorization: Bearer ${access_token}" \
    --header 'Content-Type: application/json' \
    --data "${complete_body}" \
    "${base_url}/file-upload-sessions/${session_id}/complete"
  for _ in $(seq 1 100); do
    request 200 --header "Authorization: Bearer ${access_token}" \
      "${base_url}/file-upload-sessions/${session_id}"
    status="$(jq -r '.data.status' "${response_file}")"
    if [[ "${status}" == "completed" ]]; then
      last_file_id="$(jq -r '.data.knowledge_file_id' "${response_file}")"
      last_sha256="${sha256}"
      echo "PASS upload $(basename "${file_path}") (${upload_mode})"
      return
    fi
    if [[ "${status}" == "failed" ]]; then
      jq '.data' "${response_file}" >&2
      exit 1
    fi
    sleep 0.1
  done
  echo "文件校验等待超时：$(basename "${file_path}")" >&2
  exit 1
}

delete_file() {
  local knowledge_base_id="$1"
  local file_id="$2"
  request 200 --header "Authorization: Bearer ${access_token}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}/files/${file_id}/deletion-impact"
  local token body
  token="$(jq -r '.data.confirmation_token' "${response_file}")"
  body="$(jq -nc --arg token "${token}" '{confirmation_token:$token,mode:"SOURCE_ONLY"}')"
  request 200 \
    --request DELETE \
    --header "Authorization: Bearer ${access_token}" \
    --header 'Content-Type: application/json' \
    --data "${body}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}/files/${file_id}"
}

delete_knowledge_base() {
  local knowledge_base_id="$1"
  local expected_status="${2:-200}"
  request 200 --header "Authorization: Bearer ${access_token}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}/deletion-impact"
  local token body
  token="$(jq -r '.data.confirmation_token' "${response_file}")"
  body="$(jq -nc --arg token "${token}" '{confirmation_token:$token,mode:"SOURCE_ONLY"}')"
  request "${expected_status}" \
    --request DELETE \
    --header "Authorization: Bearer ${access_token}" \
    --header 'Content-Type: application/json' \
    --data "${body}" \
    "${base_url}/knowledge-bases/${knowledge_base_id}"
}

create_fixtures
register_body="$(jq -nc --arg username "${username}" --arg password "${FILE_SMOKE_PASSWORD}" \
  '{username:$username,nickname:"文件测试用户",password:$password}')"
request 201 --header 'Content-Type: application/json' --data "${register_body}" \
  "${base_url}/auth/register"
access_token="$(jq -r '.data.access_token' "${response_file}")"
primary_access_token="${access_token}"

request 200 --header "Authorization: Bearer ${access_token}" "${base_url}/knowledge-bases"
default_knowledge_base_id="$(jq -r '.data[0].id' "${response_file}")"
request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --data '{"name":"第二知识库"}' \
  "${base_url}/knowledge-bases"
second_knowledge_base_id="$(jq -r '.data.id' "${response_file}")"

request 422 \
  --header "Authorization: Bearer ${access_token}" \
  --header "Idempotency-Key: rejected-type-${run_id}" \
  --header 'Content-Type: application/json' \
  --data '{"filename":"payload.exe","size":10}' \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/file-upload-sessions"
assert_error_key FILE_TYPE_NOT_ALLOWED
echo "PASS type whitelist 422"

request 413 \
  --header "Authorization: Bearer ${access_token}" \
  --header "Idempotency-Key: rejected-size-${run_id}" \
  --header 'Content-Type: application/json' \
  --data '{"filename":"large.pdf","size":104857601}' \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/file-upload-sessions"
assert_error_key FILE_TOO_LARGE
echo "PASS hard size limit 413"

cancel_size="$(wc -c <"${work_dir}/notes.md" | tr -d ' ')"
cancel_body="$(jq -nc --argjson size "${cancel_size}" \
  '{filename:"cancel.md",size:$size,declared_mime:"text/markdown"}')"
request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header "Idempotency-Key: cancel-${run_id}" \
  --header 'Content-Type: application/json' \
  --data "${cancel_body}" \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/file-upload-sessions"
cancel_session_id="$(jq -r '.data.session_id' "${response_file}")"
request 200 \
  --request POST \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/file-upload-sessions/${cancel_session_id}/renew-upload-url"
request 200 \
  --request DELETE \
  --header "Authorization: Bearer ${access_token}" \
  "${base_url}/file-upload-sessions/${cancel_session_id}"
[[ "$(jq -r '.data.status' "${response_file}")" == "cancelled" ]]
echo "PASS renew and cancel upload session"

uploaded_ids=()
for fixture in notes.txt notes.md resume.pdf document.docx large.docx; do
  case "${fixture}" in
    *.txt) mime="text/plain" ;;
    *.md) mime="text/markdown" ;;
    *.pdf) mime="application/pdf" ;;
    *) mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document" ;;
  esac
  upload_file "${default_knowledge_base_id}" "${work_dir}/${fixture}" "${mime}"
  uploaded_ids+=("${last_file_id}")
  if [[ "${fixture}" == "notes.txt" ]]; then
    txt_file_id="${last_file_id}"
    txt_sha256="${last_sha256}"
    txt_size="$(wc -c <"${work_dir}/${fixture}" | tr -d ' ')"
  fi
done

duplicate_body="$(jq -nc --arg sha256 "${txt_sha256}" --argjson size "${txt_size}" \
  '{filename:"notes.txt",size:$size,declared_mime:"text/plain",client_sha256:$sha256}')"
request 409 \
  --header "Authorization: Bearer ${access_token}" \
  --header "Idempotency-Key: duplicate-same-${run_id}" \
  --header 'Content-Type: application/json' \
  --data "${duplicate_body}" \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/file-upload-sessions"
assert_error_key FILE_ALREADY_ATTACHED
echo "PASS same knowledge-base duplicate 409"

request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header "Idempotency-Key: duplicate-link-${run_id}" \
  --header 'Content-Type: application/json' \
  --data "${duplicate_body}" \
  "${base_url}/knowledge-bases/${second_knowledge_base_id}/file-upload-sessions"
duplicate_session_id="$(jq -r '.data.session_id' "${response_file}")"
[[ "$(jq -r '.data.status' "${response_file}")" == "duplicate_action_required" ]]
request 200 \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --data '{"action":"LINK"}' \
  "${base_url}/file-upload-sessions/${duplicate_session_id}/duplicate-resolution"
linked_file_id="$(jq -r '.data.knowledge_file_id' "${response_file}")"
echo "PASS cross knowledge-base duplicate link"

second_register_body="$(jq -nc --arg username "${second_username}" \
  --arg password "${FILE_SMOKE_PASSWORD}" \
  '{username:$username,nickname:"隔离测试用户",password:$password}')"
request 201 --header 'Content-Type: application/json' --data "${second_register_body}" \
  "${base_url}/auth/register"
access_token="$(jq -r '.data.access_token' "${response_file}")"
request 200 --header "Authorization: Bearer ${access_token}" "${base_url}/knowledge-bases"
other_knowledge_base_id="$(jq -r '.data[0].id' "${response_file}")"
upload_file "${other_knowledge_base_id}" "${work_dir}/notes.txt" "text/plain"
other_file_id="${last_file_id}"
delete_file "${other_knowledge_base_id}" "${other_file_id}"
access_token="${primary_access_token}"
echo "PASS cross-user upload does not expose or reuse logical ownership"

request 200 --header "Authorization: Bearer ${access_token}" \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/files/${txt_file_id}/download-url"
download_url="$(jq -r '.data.url' "${response_file}")"
download_status="$(curl --silent --show-error --output /dev/null --write-out '%{http_code}' "${download_url}")"
[[ "${download_status}" == "200" ]]
echo "PASS short-lived download URL"

request 200 --header "Authorization: Bearer ${access_token}" \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/files/${txt_file_id}/deletion-impact"
stale_token="$(jq -r '.data.confirmation_token' "${response_file}")"
request 200 \
  --request PATCH \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --data '{"display_name":"notes-renamed.txt"}' \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/files/${txt_file_id}"
stale_body="$(jq -nc --arg token "${stale_token}" \
  '{confirmation_token:$token,mode:"SOURCE_ONLY"}')"
request 409 \
  --request DELETE \
  --header "Authorization: Bearer ${access_token}" \
  --header 'Content-Type: application/json' \
  --data "${stale_body}" \
  "${base_url}/knowledge-bases/${default_knowledge_base_id}/files/${txt_file_id}"
assert_error_key DELETE_PREVIEW_STALE
echo "PASS stale deletion token 409"

for file_id in "${uploaded_ids[@]}"; do
  delete_file "${default_knowledge_base_id}" "${file_id}"
done
delete_file "${second_knowledge_base_id}" "${linked_file_id}"
echo "PASS soft delete and asynchronous physical cleanup"

delete_knowledge_base "${second_knowledge_base_id}"
delete_knowledge_base "${default_knowledge_base_id}" 409
assert_error_key KNOWLEDGE_BASE_LAST_ACTIVE
echo "PASS last active knowledge-base protection 409"

echo "文件 curl smoke 全部通过；临时账号和本地文件已安排清理。"
